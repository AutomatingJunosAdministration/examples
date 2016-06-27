class ae_device_config {
    netdev_stdlib_junos::apply_group{ 'ae_device':
        template_path => "$junos_template_dir/ae_device_config.xml.erb",
    }
}
