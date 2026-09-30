"""Run as root after a separate successful SSH public-key login. Keeps Tailscale's tables intact."""
import os
import subprocess
from pathlib import Path

def run(*args): subprocess.run(args,check=True)
def write(name,value,mode=0o644):
    path=Path(name); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(value); os.chmod(path,mode)

if __name__=='__main__':
    if os.geteuid()!=0: raise SystemExit('Serve root.')
    authorized=Path('/home/dvlce/.ssh/authorized_keys').read_text()
    if 'dvlce-alba-pi' not in authorized: raise SystemExit('Verifica prima la chiave SSH di recupero.')
    write('/etc/nftables.d/alba.nft','''destroy table inet alba_guard
table inet alba_guard {
 chain input {
  type filter hook input priority -10; policy drop;
  ct state invalid counter drop
  ct state established,related accept
  iifname "lo" accept
  ip protocol icmp limit rate 20/second burst 40 packets accept
  meta l4proto ipv6-icmp accept
  udp dport 41641 accept
  udp sport 67 udp dport 68 accept
  udp sport 547 udp dport 546 accept
  iifname "tailscale0" tcp dport 22 limit rate 30/minute burst 20 packets accept
  iifname "tailscale0" tcp dport 443 accept
  counter drop
 }
 chain forward {
  type filter hook forward priority -10; policy accept;
  ct state established,related accept
  iifname != "tailscale0" iifname != "docker0" oifname "docker0" counter drop
 }
}
''')
    run('nft','--check','--file','/etc/nftables.d/alba.nft')
    write('/etc/systemd/system/alba-firewall.service','''[Unit]
Description=Alba host firewall (preserves Tailscale and Docker rules)
After=network-pre.target
Before=network.target
Wants=network-pre.target
DefaultDependencies=no
Conflicts=shutdown.target
Before=shutdown.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f /etc/nftables.d/alba.nft
ExecReload=/usr/sbin/nft -f /etc/nftables.d/alba.nft
ExecStop=-/usr/sbin/nft delete table inet alba_guard
[Install]
WantedBy=multi-user.target
''')
    write('/etc/ssh/sshd_config.d/00-alba-hardening.conf','''PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
AllowUsers dvlce
MaxAuthTries 3
MaxStartups 5:30:20
LoginGraceTime 30
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
PermitTunnel no
PermitUserEnvironment no
''')
    run('/usr/sbin/sshd','-t')
    write('/etc/sysctl.d/70-alba-security.conf','''net.ipv4.tcp_syncookies=1
net.ipv4.conf.all.accept_redirects=0
net.ipv4.conf.default.accept_redirects=0
net.ipv4.conf.all.send_redirects=0
net.ipv4.conf.default.send_redirects=0
net.ipv4.conf.all.accept_source_route=0
net.ipv4.conf.default.accept_source_route=0
net.ipv6.conf.all.accept_redirects=0
net.ipv6.conf.default.accept_redirects=0
kernel.kptr_restrict=2
kernel.dmesg_restrict=1
kernel.unprivileged_bpf_disabled=1
fs.protected_hardlinks=1
fs.protected_symlinks=1
''')
    write('/etc/fail2ban/jail.d/alba.local','''[sshd]
enabled=true
backend=systemd
maxretry=4
findtime=10m
bantime=1h
banaction=nftables-multiport
''')
    write('/etc/apt/apt.conf.d/52alba-security','''APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Origins-Pattern {
 "origin=Debian,codename=${distro_codename},label=Debian";
 "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";
};
Unattended-Upgrade::Automatic-Reboot "false";
''')
    # The timed rollback protects against losing SSH. Cancel only after a fresh key login and HTTPS test.
    write('/root/alba-security-rollback.py','''import subprocess
from pathlib import Path
Path('/etc/ssh/sshd_config.d/00-alba-hardening.conf').unlink(missing_ok=True)
subprocess.run(['systemctl','disable','--now','alba-firewall.service'])
subprocess.run(['systemctl','reload','ssh.service'])
''',0o600)
    run('systemctl','daemon-reload')
    run('systemd-run','--unit=alba-security-rollback','--on-active=3m','/usr/bin/python3','/root/alba-security-rollback.py')
    run('systemctl','enable','--now','alba-firewall.service')
    run('systemctl','reload','ssh.service')
    run('sysctl','-p','/etc/sysctl.d/70-alba-security.conf')
    run('systemctl','restart','fail2ban.service')
    run('systemctl','enable','--now','apt-daily.timer','apt-daily-upgrade.timer')
    run('systemctl','disable','--now','avahi-daemon.service','avahi-daemon.socket')
    print('Protezione applicata. Verificare SSH con chiave/HTTPS, poi fermare alba-security-rollback.timer.')
