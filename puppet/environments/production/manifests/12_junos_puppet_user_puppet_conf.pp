class junos_puppet_user_puppet_conf {
  notify { 'puppet.conf':
    message => "Maintaining puppet.conf on $hostname"
  }
  file { "$junos_puppet_dir":
    ensure => directory,
    owner => $id,
    mode => 0755,
  }
  file { "$junos_puppet_dir/puppet.conf":
    ensure => file,
    owner => $id,
    mode => 0644,
    content => template("$junos_template_dir/puppet_agent_conf.erb")
  }
}
