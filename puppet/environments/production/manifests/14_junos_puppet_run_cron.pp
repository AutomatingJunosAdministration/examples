class junos_puppet_run_cron {
  notify { 'puppet_cron':
    message => "Maintaining Puppet cron entry on $hostname"
  }
  cron { puppetrun:
      ensure => absent,
      environment => "PATH=${path}",
      command => "puppet agent -v -o --no-daemonize > $junos_run_log 2>&1",
      user => "$id",
      minute => "*/$junos_puppet_run_frequency",
  }
}
