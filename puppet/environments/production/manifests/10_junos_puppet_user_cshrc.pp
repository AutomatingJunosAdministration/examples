class junos_puppet_user_cshrc {
  $puppet_path = '/opt/sdk/juniper/bin'
  notify { 'cshrc':
    message => "Maintaining .cshrc on $hostname"
  }
  file { "$junos_home_dir/.cshrc":
    ensure => file,
    owner => $id,
    mode => 0644,
    content => "setenv PATH \${PATH}:$puppet_path\n",
  }
}
