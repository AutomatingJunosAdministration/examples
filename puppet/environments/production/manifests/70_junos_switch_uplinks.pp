class junos_switch_uplinks {
  if $junos_personality == 'JUNOS_switch' {
    netdev_vlan { 'net_mgmt': vlan_id => 99, description => 'Net Management' }
    Netdev_interface {
      ensure => present,
      active => true,
      admin => up,
    }
    Netdev_lag {
      ensure => present,
      active => true,
      lacp => active,
      minimum_links => '1',
    }
    $ae_count = 2
    include ae_device_config
    if $hardwaremodel =~ /^qfx5100-48s-6q$/ {
      notify { 'Uplinks':
        message => "Hardware: $hardwaremodel Uplinks: et-0/0/[50-53]"
      }
      netdev_interface {
        'et-0/0/50':
          description => 'Uplink 0 Member 0',
        ;
        'et-0/0/51':
          description => 'Uplink 0 Member 1',
        ;
        'et-0/0/52':
          description => 'Uplink 1 Member 0',
        ;
        'et-0/0/53':
          description => 'Uplink 1 Member 1',
        ;
      }
      netdev_l2_interface { [ 'et-0/0/50','et-0/0/51','et-0/0/52','et-0/0/53' ]:
        ensure => absent,
      }
      netdev_lag {
        'ae0':
          links => [ 'et-0/0/50','et-0/0/51' ],
        ;
        'ae1':
          links => [ 'et-0/0/52','et-0/0/53' ],
        ;
      }
    }
    elsif $hardwaremodel =~ /^qfx5100/ {
      notify { 'Uplinks':
        message => "Hardware: $hardwaremodel Uplinks: et-0/0/[0-3]"
      }
      netdev_interface { 'et-0/0/0':
        description => 'Uplink 0 Member 0',
      }
      netdev_interface { 'et-0/0/1':
        description => 'Uplink 0 Member 1',
      }
      netdev_interface { 'et-0/0/2':
        description => 'Uplink 1 Member 0',
      }
      netdev_interface { 'et-0/0/3':
        description => 'Uplink 1 Member 1',
      }
      netdev_l2_interface { [ 'et-0/0/0','et-0/0/1','et-0/0/2','et-0/0/3' ]:
        ensure => absent,
      }
      netdev_lag { 'ae0':
        links => [ 'et-0/0/0','et-0/0/1' ],
      }
      netdev_lag { 'ae1':
        links => [ 'et-0/0/2','et-0/0/3' ],
      }
    }
    else {
      fail("Unrecognized Junos switch model $hardwaremodel")
    }
  }
}
