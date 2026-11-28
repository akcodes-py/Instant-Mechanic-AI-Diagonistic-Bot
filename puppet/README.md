# Puppet (configuration artifact)

`manifests/site.pp` provisions an EC2 host with Docker, Nginx and the reverse
proxy in `ec2-nginx.conf`. It is **not applied or verified**: no Puppet server or
agent exists on this machine or in CI. A deployment is only real after the live
host passes `/api/health/` and the full chat/diagnosis/booking/dispatch flow.

When Puppet is available:

```powershell
puppet parser validate puppet/manifests/site.pp
```

The manifest needs the `puppetlabs-firewall` module for the `firewall` resource.
Update `docs/DEPLOYMENT.md` before relying on it in production.
