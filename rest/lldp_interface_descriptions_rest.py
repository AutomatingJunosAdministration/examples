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
import email
import getpass

import requests
import jxmlease

# Should be set appropriately for the network environment.
SCHEME = 'http'
PORT = 3000

SINGLE_RPC_URL_FORMAT = SCHEME + '://%s:' + str(PORT) + '/rpc/%s@format=%s'
MULTIPLE_RPC_URL_FORMAT = SCHEME + '://%s:' + str(PORT) + '/rpc'

# Create a jxmlease parser with desired defaults.
parser = jxmlease.Parser()


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

    for device in sys.argv[1:]:
        print("Getting LLDP information from %s..." % device)
        lldp_info = get_lldp_neighbors(device=device, user=user, pw=password)
        if not lldp_info:
            if lldp_info == None:
                print("    Error retrieving LLDP info on " + device +
                      ". Make sure LLDP is enabled.")
            else:
                print("    No LLDP neighbors on " + device +
                      "Make sure LLDP is enabled." % device)
            rc = 1
            continue

        print("Getting interface descriptions from %s..." % device)
        desc_info = get_description_info_for_interfaces(device=device,
                                                        user=user,
                                                        pw=password)
        if desc_info == None:
            print("    Error retrieving interface descriptions on %s." % device)
            rc = 1
            continue

        desc_changes = check_lldp_changes(lldp_info, desc_info)
        if not desc_changes:
            print("    No LLDP changes to configure on %s." % device)
            continue

        config = build_config_changes(desc_changes)
        if config == None:
            print("    Error generating configuration changes for %s." % device)
            rc = 1
            continue

        if load_merge_xml_config(device=device,
                                 user=user,
                                 pw=password,
                                 config=config):
            print("    Sucessfully committed configuration changes on %s." %
                  device)
        else:
            print("    Error committing description changes on %s." % device)
            rc = 1
    return rc


def get_lldp_neighbors(device=None, user=None, pw=None):
    """Get current LLDP neighbor information.

    Return a two-level dictionary with the LLDP neighbor information..
    The first-level key is the local port (aka interface) name.
    The second-level keys are 'system' for the remote system name
    and 'port' for the remote port ID. On error, return None.

    For example:
    {'ge-0/0/1': {'system': 'r1', 'port', 'ge-0/0/10'}}
    """

    url = SINGLE_RPC_URL_FORMAT % (device,
                                   'get-lldp-neighbors-information',
                                   'json')

    http_resp = requests.get(url, auth=(user,pw))
    http_resp.raise_for_status()

    # Check for an XML error message.
    if http_resp.headers['Content-Type'].startswith('application/xml'):
        _ = check_for_warnings_and_errors(parser(http_resp.text))
        return None

    resp = http_resp.json()
    
    lldp_info = {}
    try:
        ni = resp['lldp-neighbors-information'][0]['lldp-neighbor-information']
    except KeyError:
        return None

    for nbr in ni:
        try:
            local_port = nbr['lldp-local-port-id'][0]['data']
            remote_system = nbr['lldp-remote-system-name'][0]['data']
            remote_port = nbr['lldp-remote-port-id'][0]['data']
            lldp_info[local_port] = {'system': remote_system,
                                     'port': remote_port}
        except KeyError:
            return None

    return lldp_info


def get_description_info_for_interfaces(device=None, user=None, pw=None):
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

    url = SINGLE_RPC_URL_FORMAT % (device, 'get-interface-information', 'xml')

    http_resp = requests.get(url,
                             auth=(user, pw),
                             params={'descriptions': ''},
                             stream=True)
    http_resp.raise_for_status()
    resp = parser(http_resp.raw)

    (error_count, warning_count) = check_for_warnings_and_errors(resp)
    if error_count > 0:
        return None

    desc_info = {}
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


def check_for_warnings_and_errors(root):
    """Check a jxmlease.XMLDictNode for warnings and errors.

    Prints the warning or error message.
    (Note: Ignores the warning:
           'uncommitted changes will be discarded on exit'
           This warning is an expected output of the open-configuration RPC.)

    Returns a tuple of (error_count, warning_count).
    """

    error_count = 0
    warning_count = 0
    for node in root.find_nodes_with_tag(('xnm:warning','xnm:error')):
        msg = node.get('message','(empty message)')
        if node.tag == 'xnm:warning':
            if msg == 'uncommitted changes will be discarded on exit': 
                continue
            level = 'Warning'   
            warning_count += 1
        elif node.tag == 'xnm:error':
            level = 'Error'
            error_count += 1
        else:
            level = 'Unknown'
        print "    %s: %s" % (level,msg)
    return (error_count, warning_count)


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


def build_config_changes(desc_changes):
    """Generate a configuration snippet with new interface descriptions.

    Given a dictionary of new description values to be configured, build
    a configuration snippet as a jxmlease.XMLDictNode. The configuration
    snippet will configure the new description for each interface.

    Return the configuration snippet as a jxmlease.XMLDictNode.
    """

    interface_list = []
    for local_port in desc_changes:
        interface_list.append({'name': local_port,
                               'description': desc_changes[local_port]})
    config = {'configuration': {'interfaces': {'interface':interface_list}}}
    return jxmlease.XMLDictNode(config)


def load_merge_xml_config(device=None, user=None, pw=None, config=None):
    """Load a configuration using "configure private" and "load merge".

    Given a configuration snippet as a jxmlease.XMLDictNode, do:
        configure private,
        load merge of the config snippet,
        commit (and close the configuration),
        and check the results.

    Return True if the config was committed successfully, False otherwise.
    """

    load_config_node = jxmlease.XMLDictNode(config, tag='load-configuration')
    load_config_node.set_xml_attr('action', 'merge')
    load_config_node.set_xml_attr('format', 'xml')

    rpcs = []
    rpcs.append({'open-configuration':{'private':''}})
    rpcs.append(load_config_node)
    rpcs.append({'commit-configuration':''})
    rpcs.append({'close-configuration':''})
    payload_string = jxmlease.XMLListNode(rpcs).emit_xml(full_document=False)

    args = {'stop-on-error':'1'}
    headers = {'Accept': 'application/xml',
               'Content-Type': 'application/xml'}
    url = MULTIPLE_RPC_URL_FORMAT % (device)
    http_resp = requests.post(url, auth=(user,pw), params=args,
                              headers=headers, data=payload_string)
    http_resp.raise_for_status()

    responses = parse_multipart_messages(type=http_resp.headers['Content-Type'],
                                         response=http_resp.text)

    rc = True

    if len(responses) != len(rpcs):
        print "    Error: Fewer responses than expected!"
        rc = False

    for xml_response in responses:
        if xml_response == None:
            print "    Error: Unable to parse an RPC response!"
            rc = False
        else:
            (error_count, warning_count) = check_for_warnings_and_errors(
                parser(xml_response)
            )
            if error_count > 0:
                rc = False

    return rc


def parse_multipart_messages(type=None, response=None):
    """Parse the response from a multi-RPC API call.

    Parse the response from a multi-RPC API call into a list of the
    individual messages.

    Note: Some RPCs return an empty response. In this case, there is no
          content type or payload. In this case, the email package returns
          the default content type of text/plain. This case is expected, and
          not an error.

    Return a list of messages on success. If there is a problem parsing a
    message, the value of the message is None.
    """

    # Add a MIME header to allow the email package to correctly parse
    # the remainder of the message.
    msg = email.message_from_string('Content-Type: %s\n\n%s' % (type,response))

    if not msg.is_multipart():
        return [msg.get_payload(decode=True)]

    # Iterate over the message parts and add them to the list.
    msg_list = []
    for sub_msg in msg.get_payload():
        payload = sub_msg.get_payload(decode=True)
        sub_type = sub_msg.get_content_type()
        if (sub_type == 'application/xml' or
            sub_type == 'application/json' or
            (sub_type == 'text/plain' and payload == "")):
            msg_list.append(payload)
        else:
            print("    Error: Unknown sub message.\n" +
                  "           Type: %s\n" +
                  "           Content: %s" % (sub_type,payload))
            msg_list.append(None)
    return msg_list


if __name__ == "__main__":
  sys.exit(main())
