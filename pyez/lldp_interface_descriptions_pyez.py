#!/usr/bin/env python
"""Use interface descriptions to track the topology reported by LLDP.

This includes the following steps:
1) Gather LLDP neighbor information.
2) Gather interface descriptions.
3) Parse LLDP neighbor information previously stored in the descriptions.
4) Compare LLDP neighbor info to previous LLDP info from the description.
5) Print LLDP Up / Change / Down events.
6) Store the updated LLDP neighbor info in the interface description.

Interface descriptions are in the format:
[user configured description ]LLDP: <remote system> <remote port>[(DOWN)]

The '(DOWN)' string indicates an LLDP neighbor which was previously
present, but is now not present.
"""

import sys
import getpass

import jxmlease

from jnpr.junos import Device
from jnpr.junos.utils.config import Config
import jnpr.junos.exception

TEMPLATE_PATH = 'interface_descriptions_template.xml'

# Create a jxmlease parser with desired defaults.
parser = jxmlease.EtreeParser()

class DoneWithDevice(Exception): pass

def main():
    """The main loop.

    Prompt for a username and password.
    Loop over each device specified on the command line.
    Perform the following steps on each device:
    1) Get LLDP information from the current device state.
    2) Get interface descriptions from the device configuration.
    3) Compare the LLDP information against the previous snapshot of LLDP
       information stored in the interface descriptions. Print changes.
    4) Build a configuration snippet with new interface descriptions.
    5) Commit the configuration changes.

    Return an integer suitable for passing to sys.exit().
    """

    if len(sys.argv) == 1:
        print("\nUsage: %s device1 [device2 [...]]\n\n" % sys.argv[0])
        return 1

    rc = 0

    # Get username and password as user input.
    user = raw_input('Device Username: ')
    password = getpass.getpass('Device Password: ')

    for hostname in sys.argv[1:]:
        try:
            print("Connecting to %s..." % hostname)
            dev = Device(host=hostname,
                         user=user,
                         password=password,
                         normalize=True)
            dev.open()

            print("Getting LLDP information from %s..." % hostname)
            lldp_info = get_lldp_neighbors(device=dev)
            if not lldp_info:
                if lldp_info == None:
                    print("    Error retrieving LLDP info on " + hostname +
                          ". Make sure LLDP is enabled.")
                    rc = 1
                else:
                    print("    No LLDP neighbors on " + hostname +
                          ". Make sure LLDP is enabled.")
                raise DoneWithDevice

            print("Getting interface descriptions from %s..." % hostname)
            desc_info = get_description_info_for_interfaces(device=dev)
            if desc_info == None:
                print("    Error retrieving interface descriptions on %s." %
                      hostname)
                rc = 1
                raise DoneWithDevice

            desc_changes = check_lldp_changes(lldp_info, desc_info)
            if not desc_changes:
                print("    No LLDP changes to configure on %s." % hostname)
                raise DoneWithDevice

            if load_merge_template_config(
                device=dev,
                template_path=TEMPLATE_PATH,
                template_vars={'descriptions': desc_changes}):
                print("    Sucessfully committed configuration changes on %s." %
                      hostname)
            else:
                print("    Error committing description changes on %s." %
                      hostname)
                rc = 1
                raise DoneWithDevice
        except jnpr.junos.exception.ConnectError as err:
            print("    Error connecting: " + repr(err))
            rc = 1
        except DoneWithDevice:
            pass
        finally:
            print("    Closing connection to %s." % hostname)
            try:
                dev.close()
            except:
                pass
    return rc


def get_lldp_neighbors(device):
    """Get current LLDP neighbor information.

    Return a two-level dictionary with the LLDP neighbor information..
    The first-level key is the local port (aka interface) name.
    The second-level keys are 'system' for the remote system name
    and 'port' for the remote port ID. On error, return None.

    For example:
    {'ge-0/0/1': {'system': 'r1', 'port', 'ge-0/0/10'}}
    """

    lldp_info = {}
    try:
        resp = device.rpc.get_lldp_neighbors_information()
    except (jnpr.junos.exception.RpcError,
            jnpr.junos.exception.ConnectError)as err:
        print "    " + repr(err)
        return None

    for nbr in resp.findall('lldp-neighbor-information'):
        local_port = nbr.findtext('lldp-local-port-id')
        remote_system = nbr.findtext('lldp-remote-system-name')
        remote_port = nbr.findtext('lldp-remote-port-id')
        if local_port and (remote_system or remote_port):
            lldp_info[local_port] = {'system': remote_system,
                                     'port': remote_port}

    return lldp_info

def get_description_info_for_interfaces(device):
    """Get current interface description for each interface.

    Parse the description into the user-configured description, remote
    system and remote port components.

    Return a two-level dictionary. The first-level key is the
    local port (aka interface) name. The second-level keys are
    'user_desc' for the user-configured description, 'system' for the
    remote system name, 'port' for the remote port, and 'down' which is
    a boolean indicating if LLDP was previously down. On error, return None.

    For example:
    {'ge-0/0/1': {'user_desc': 'test description', 'system': 'r1',
                  'port': 'ge-0/0/10', 'down': True}}
    """

    desc_info = {}
    try:
        resp = parser(device.rpc.get_interface_information(descriptions=True))
    except (jnpr.junos.exception.RpcError,
            jnpr.junos.exception.ConnectError) as err:
        print "    " + repr(err)
        return None

    try:
        pi = resp['interface-information']['physical-interface'].jdict()
    except KeyError:
        return desc_info

    for (local_port, port_info) in pi.items():
        try:
            (udesc, _, ldesc) = port_info['description'].partition('LLDP: ')
            udesc = udesc.rstrip()
            (remote_system, _, remote_port) = ldesc.partition(' ')
            (remote_port, down_string, _) = remote_port.partition('(DOWN)')
            desc_info[local_port] = {'user_desc': udesc,
                                     'system': remote_system,
                                     'port': remote_port,
                                     'down': True if down_string else False}
        except (KeyError, TypeError):
            pass
    return desc_info


def check_lldp_changes(lldp_info, desc_info):
    """Compare current LLDP info with previous snapshot from descriptions.

    Given the dictionaries produced by get_lldp_neighbors() and
    get_description_info_for_interfaces(), print LLDP up, change,
    and down messages.

    Return a dictionary containing information for the new descriptions
    to configure.
    """

    desc_changes = {}

    # Iterate through the current LLDP neighbor state. Compare this
    # to the saved state as retreived from the interface descriptions.
    for local_port in lldp_info:
        lldp_system = lldp_info[local_port]['system']
        lldp_port = lldp_info[local_port]['port']
        has_lldp_desc = desc_info.has_key(local_port)
        if has_lldp_desc:
            desc_system = desc_info[local_port]['system']
            desc_port = desc_info[local_port]['port']
            down = desc_info[local_port]['down']
            if not desc_system or not desc_port:
                has_lldp_desc = False
        if not has_lldp_desc:
            print("    %s LLDP Up. Now: %s %s" %
                  (local_port,lldp_system,lldp_port))
        elif down:
            print("    %s LLDP Up. Was: %s %s Now: %s %s" %
                  (local_port,desc_system,desc_port,lldp_system,lldp_port))
        elif lldp_system != desc_system or lldp_port != desc_port:
            print("    %s LLDP Change. Was: %s %s Now: %s %s" %
                  (local_port,desc_system,desc_port,lldp_system,lldp_port))
        else:
            # No change. LLDP was not down. Same system and port.
            continue
        desc_changes[local_port] = "LLDP: %s %s" % (lldp_system,lldp_port)

    # Iterate through the saved state as retrieved from the interface
    # descriptions. Look for any neighbors that are present in the
    # saved state, but are not present in the current LLDP neighbor
    # state.
    for local_port in desc_info:
        desc_system = desc_info[local_port]['system']
        desc_port = desc_info[local_port]['port']
        down = desc_info[local_port]['down']
        if (desc_system and desc_port and not down and
            not lldp_info.has_key(local_port)):
            print("    %s LLDP Down. Was: %s %s" %
                  (local_port,desc_system,desc_port))
            desc_changes[local_port] = "LLDP: %s %s(DOWN)" % (desc_system,
                                                              desc_port)

    # Iterate through the list of interface descriptions we are going
    # to change. Prepend the user description, if any.
    for local_port in desc_changes:
        try:
            udesc = desc_info[local_port]['user_desc']
        except KeyError:
            continue
        if udesc:
            desc_changes[local_port] = udesc + " " + desc_changes[local_port]

    return desc_changes


def load_merge_template_config(device,
                               template_path,
                               template_vars):
    """Load templated config with "configure private" and "load merge".

    Given a template_path and template_vars, do:
        configure private,
        load merge of the templated config,
        commit,
        and check the results.

    Return True if the config was committed successfully, False otherwise.
    """

    class LoadNotOKError(Exception): pass

    device.bind(cu=Config)

    rc = False

    try:
        try:
            resp = device.rpc.open_configuration(private=True)
        except jnpr.junos.exception.RpcError as err:
            if not (err.rpc_error['severity'] == 'warning' and
                    'uncommitted changes will be discarded on exit' in
                    err.rpc_error['message']):
                raise

        resp = device.cu.load(template_path=template_path,
                              template_vars=template_vars,
                              merge=True)
        if resp.find("ok") is None:
            raise LoadNotOKError
        device.cu.commit(comment="made by %s" % sys.argv[0])
    except (jnpr.junos.exception.RpcError,
            jnpr.junos.exception.ConnectError,
            LoadNotOKError) as err:
        print "    " + repr(err)
    except:
        print "    Unknown error occured loading or committing configuration."
    else:
        rc = True
    try:
        device.rpc.close_configuration()
    except jnpr.junos.exception.RpcError as err:
        print "    " + repr(err)
        rc = False
    return rc


if __name__ == "__main__":
  sys.exit(main())
