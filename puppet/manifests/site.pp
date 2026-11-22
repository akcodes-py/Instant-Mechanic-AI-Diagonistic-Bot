# EC2 + Nginx provisioning for the H3 dispatch platform (ADR-001).
# Configuration artifact only: no Puppet server was available to apply this.
# Verify with `puppet parser validate puppet/manifests/site.pp` when Puppet exists.

 node default {
   $app_dir = '/opt/instant-mechanic'

   package { 'docker':
     ensure => installed,
   }

   service { 'docker':
     ensure     => running,
     enable     => true,
     require    => Package['docker'],
   }

   package { 'nginx':
     ensure => installed,
   }

   file { "${app_dir}/ec2-nginx.conf":
     ensure  => file,
     source  => 'puppet:///modules/instant_mechanic/ec2-nginx.conf',
     require => Package['nginx'],
   }

   file { '/etc/nginx/sites-available/instant-mechanic':
     ensure  => link,
     target  => "${app_dir}/ec2-nginx.conf",
     require => File["${app_dir}/ec2-nginx.conf"],
     notify  => Service['nginx'],
   }

   service { 'nginx':
     ensure  => running,
     enable  => true,
     require => Package['nginx'],
   }

   # TLS is terminated here. The FastAPI app does NOT redirect HTTP itself.
   firewall { '100 allow http/https':
     proto  => 'tcp',
     dport  => [80, 443],
     action => 'accept',
   }
 }
