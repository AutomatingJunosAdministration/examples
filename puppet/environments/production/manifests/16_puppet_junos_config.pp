class puppet_junos_config {
    netdev_stdlib_junos::apply_group{ 'puppet':
        ensure => present,
        active => true,
        template_path => "$junos_template_dir/puppet_junos_config.text.erb",
    }
}
