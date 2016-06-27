node 's0.example.com' {

  $customer_vlans = {
    'accounting' => { vlan_id => 100, description => 'Accounting Department' },
    'hardware'   => { vlan_id => 101, description => 'Hardware Engineering' },
    'software'   => { vlan_id => 102, description => 'Software Development' },
  }

  $customer_ports = {
    'et-0/0/0' => { untagged_vlan => 'accounting' },
    'et-0/0/1' => { untagged_vlan => 'software' },
    'et-0/0/2' => { untagged_vlan => 'hardware' },
  }

  create_resources( netdev_vlan, $customer_vlans )

  create_resources( netdev_l2_interface, $customer_ports )

  netdev_l2_interface { [ 'ae0','ae1' ]:
    untagged_vlan => 'net_mgmt',
    tagged_vlans => keys( $customer_vlans ),
  }
}
