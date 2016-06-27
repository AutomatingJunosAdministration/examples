$junos_home_dir = "/var/home/$id"

$junos_puppet_dir = "$junos_home_dir/.puppet"

# Frequency, in minutes, to execute the puppet agent.
# Must be between 1 and 60.
$junos_puppet_run_frequency = '5'

$junos_run_log = '/tmp/puppet_run.log'

$junos_template_dir = '/etc/puppet/files/junos_templates'
