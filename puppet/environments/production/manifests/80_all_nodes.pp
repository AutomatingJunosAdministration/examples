case $operatingsystem {
  'JUNOS': {
    netdev_device { $hostname: }
    include junos_puppet_user_cshrc
    include junos_puppet_user_puppet_conf
    include junos_puppet_run_cron
    include junos_switch_uplinks
    include puppet_junos_config
  }
  default: {
    fail('Unknown operating system!')
  }
}
