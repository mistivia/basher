quiet
# This file is overwritten during software install.
# Persistent customizations should go in a .local file.
include disable-programs.local

blacklist ${RUNUSER}/*firefox*
blacklist ${RUNUSER}/*floorp*
blacklist ${RUNUSER}/akonadi
blacklist ${RUNUSER}/i3
blacklist ${RUNUSER}/psd/*firefox*
blacklist ${RUNUSER}/psd/*floorp*
blacklist ${RUNUSER}/qutebrowser
blacklist /etc/clamav
blacklist /etc/ssmtp
blacklist /tmp/.wine-*
blacklist /tmp/akonadi-*
blacklist /tmp/evolution-*
blacklist /tmp/i3-*
blacklist /tmp/lwjgl_*
blacklist /var/games/nethack
blacklist /var/games/slashem
blacklist /var/games/vulturesclaw
blacklist /var/games/vultureseye
blacklist /var/lib/games/Maelstrom-Scores
blacklist /var/lib/mpd
# This file is overwritten during software install.
# Persistent customizations should go in a .local file.
include disable-common.local

# The following block breaks trash functionality in file managers

blacklist-nolog /tmp/clipmenu*

# X11 session autostart
# this will kill --x11=xpra cmdline option for all programs
blacklist /etc/X11/Xsession.d
blacklist /etc/X11/xinit
blacklist /etc/X11/xorg.conf.d
blacklist /etc/xdg/autostart
blacklist /var/log/Xorg.*

# Session manager
# see #3358
#?HAS_X11: blacklist /tmp/.ICE-unix

# KDE config
blacklist /tmp/konsole-*.history

# KDE sockets
blacklist ${RUNUSER}/*.slave-socket
blacklist ${RUNUSER}/kdeinit5__*
blacklist ${RUNUSER}/kdesud_*
# see #3358
#?HAS_NODBUS: blacklist ${RUNUSER}/ksocket-*
#?HAS_NODBUS: blacklist /tmp/ksocket-*

# gnome
# contains extensions, last used times of applications, and notifications
# contains recently used files and serials of static/removable storage
# no direct modification of dconf database
blacklist ${RUNUSER}/gnome-session-leader-fifo
blacklist ${RUNUSER}/gnome-shell
blacklist ${RUNUSER}/gsconnect

# i3 IPC socket (allows arbitrary shell script execution)
blacklist ${RUNUSER}/i3/ipc-socket.*
blacklist /tmp/i3-*/ipc-socket.*

# sway IPC socket (allows arbitrary shell script execution)
blacklist ${RUNUSER}/sway-ipc.*
blacklist /tmp/sway-ipc.*

# systemd
blacklist ${PATH}/systemctl
blacklist ${PATH}/systemd*
blacklist ${RUNUSER}/systemd
blacklist /etc/credstore*
blacklist /etc/systemd/network
blacklist /etc/systemd/system
blacklist /run/credentials
blacklist /var/lib/systemd
# creates problems on Arch where /etc/resolv.conf is a symlink to /var/run/systemd/resolve/resolv.conf
#blacklist /var/run/systemd

# openrc
blacklist /etc/init.d
blacklist /etc/rc.conf
blacklist /etc/runlevels

# VirtualBox

# GNOME Boxes

# libvirt
blacklist ${RUNUSER}/libvirt
blacklist /var/cache/libvirt
blacklist /var/lib/libvirt
blacklist /var/log/libvirt

# OCI-Containers / Podman
blacklist ${RUNUSER}/containers
blacklist ${RUNUSER}/crun
blacklist ${RUNUSER}/libpod
blacklist ${RUNUSER}/runc
blacklist ${RUNUSER}/toolbox

# VeraCrypt
blacklist ${PATH}/veracrypt
blacklist ${PATH}/veracrypt-uninstall.sh
blacklist /usr/share/applications/veracrypt.*
blacklist /usr/share/pixmaps/veracrypt.*
blacklist /usr/share/veracrypt

# TrueCrypt
blacklist ${PATH}/truecrypt
blacklist ${PATH}/truecrypt-uninstall.sh
blacklist /usr/share/applications/truecrypt.*
blacklist /usr/share/pixmaps/truecrypt.*
blacklist /usr/share/truecrypt

# zuluCrypt
blacklist ${PATH}/zuluCrypt-cli
blacklist ${PATH}/zuluMount-cli

# var
blacklist /var/cache/apt
blacklist /var/cache/pacman
blacklist /var/lib/apt
blacklist /var/lib/clamav
blacklist /var/lib/dkms
blacklist /var/lib/mysql/mysql.sock
blacklist /var/lib/mysqld/mysql.sock
blacklist /var/lib/pacman
blacklist /var/lib/upower
# a virtual /var/log directory (mostly empty) is build up by default for every
# sandbox, unless --writable-var-log switch is activated
#blacklist /var/log
blacklist /var/mail
blacklist /var/opt
blacklist /var/run/acpid.socket
blacklist /var/run/docker.sock
blacklist /var/run/minissdpd.sock
blacklist /var/run/mysql/mysqld.sock
blacklist /var/run/mysqld/mysqld.sock
blacklist /var/run/rpcbind.sock
blacklist /var/run/screens
blacklist /var/spool/anacron
blacklist /var/spool/cron
blacklist /var/spool/mail

# etc
blacklist /etc/adduser.conf
blacklist /etc/anacrontab
blacklist /etc/apparmor*
blacklist /etc/cron*
blacklist /etc/default
blacklist /etc/dkms
blacklist /etc/grub*
blacklist /etc/kernel*
blacklist /etc/logrotate*
blacklist /etc/modules*
blacklist /etc/rc.local
# rc1.d, rc2.d, ...
blacklist /etc/rc?.d
blacklist /etc/sysconfig

# hide config for various intrusion detection systems
blacklist /etc/aide
blacklist /etc/aide.conf
blacklist /etc/chkrootkit.conf
blacklist /etc/fail2ban.conf
blacklist /etc/logcheck
blacklist /etc/lynis
blacklist /etc/rkhunter.*
blacklist /etc/snort
blacklist /etc/suricata
blacklist /etc/tripwire
blacklist /var/lib/rkhunter

# Startup files

# Remote access (used only by sshd; should always be blacklisted)
blacklist /etc/hosts.equiv

# Initialization files that allow arbitrary command execution

# System package managers and AUR helpers

# Make directories commonly found in $PATH read-only

# Write-protection for portable apps

# Write-protection for desktop entries


# Configuration files that do not allow arbitrary command execution but that
# are intended to be modified manually (in a text editor and/or by a program
# dedicated to managing them)

# Write-protection for thumbnailer dir

# prevent access to ssh-agent
blacklist ${RUNUSER}/openssh_agent
blacklist /tmp/ssh-*

# top secret
blacklist /.fscrypt
blacklist /etc/davfs2/secrets
blacklist /etc/doas.conf
blacklist /etc/group+
blacklist /etc/group-
blacklist /etc/gshadow
blacklist /etc/gshadow+
blacklist /etc/gshadow-
blacklist /etc/msmtprc
blacklist /etc/passwd+
blacklist /etc/passwd-
blacklist /etc/shadow
blacklist /etc/shadow+
blacklist /etc/shadow-
blacklist /etc/ssh
blacklist /etc/ssh/*
blacklist /etc/sudo*.conf
blacklist /etc/sudoers*
blacklist /home/.ecryptfs
blacklist /home/.fscrypt
blacklist /run/timeshift
blacklist /var/backup

# dm-crypt / LUKS
blacklist /crypto_keyfile.bin

# Remove environment variables with auth tokens.
# Note however that the sandbox might still have access to the
# files where these variables are set.
rmenv GH_TOKEN
rmenv GITHUB_TOKEN
rmenv GH_ENTERPRISE_TOKEN
rmenv GITHUB_ENTERPRISE_TOKEN
rmenv CARGO_REGISTRY_TOKEN
rmenv RESTIC_KEY_HINT
rmenv RESTIC_PASSWORD_COMMAND
rmenv RESTIC_PASSWORD_FILE

# cloud provider configuration
blacklist /etc/boto.cfg

# system directories
blacklist /sbin
blacklist /usr/local/sbin
blacklist /usr/sbin

# system management and various SUID executables
blacklist ${PATH}/at
blacklist ${PATH}/bmon
blacklist ${PATH}/busybox
blacklist ${PATH}/chage
blacklist ${PATH}/chfn
blacklist ${PATH}/chsh
blacklist ${PATH}/crontab
blacklist ${PATH}/doas
blacklist ${PATH}/evtest
blacklist ${PATH}/expiry
blacklist ${PATH}/fping
blacklist ${PATH}/fping6
blacklist ${PATH}/fusermount*
blacklist ${PATH}/gksu
blacklist ${PATH}/gksudo
blacklist ${PATH}/gpasswd
blacklist ${PATH}/groupmems
blacklist ${PATH}/hostname
#blacklist ${PATH}/ip # breaks --ip=dhcp
blacklist ${PATH}/kdesudo
blacklist ${PATH}/ksu
blacklist ${PATH}/mount
blacklist ${PATH}/mount.*
blacklist ${PATH}/mountpoint
blacklist ${PATH}/mtr
blacklist ${PATH}/mtr-packet
blacklist ${PATH}/nc
blacklist ${PATH}/nc.openbsd
blacklist ${PATH}/nc.traditional
blacklist ${PATH}/ncat
blacklist ${PATH}/netstat
blacklist ${PATH}/networkctl
blacklist ${PATH}/newgidmap
blacklist ${PATH}/newgrp
blacklist ${PATH}/newuidmap
blacklist ${PATH}/nm-online
blacklist ${PATH}/nmap
blacklist ${PATH}/nmcli
blacklist ${PATH}/nmtui
blacklist ${PATH}/nmtui-connect
blacklist ${PATH}/nmtui-edit
blacklist ${PATH}/nmtui-hostname
blacklist ${PATH}/ntfs-3g
blacklist ${PATH}/passwd
blacklist ${PATH}/physlock
blacklist ${PATH}/pkexec
blacklist ${PATH}/plocate
blacklist ${PATH}/pmount
blacklist ${PATH}/procmail
blacklist ${PATH}/pumount
blacklist ${PATH}/schroot
blacklist ${PATH}/sg
blacklist ${PATH}/slock
blacklist ${PATH}/ss
blacklist ${PATH}/ssmtp
blacklist ${PATH}/strace
blacklist ${PATH}/su
blacklist ${PATH}/sudo
blacklist ${PATH}/suexec
blacklist ${PATH}/tcpdump
blacklist ${PATH}/traceroute
blacklist ${PATH}/umount
blacklist ${PATH}/unix_chkpwd
blacklist ${PATH}/wall
blacklist ${PATH}/write
blacklist ${PATH}/wshowkeys
blacklist ${PATH}/xev
blacklist ${PATH}/xinput
blacklist /usr/lib/chromium/chrome-sandbox
blacklist /usr/lib/dbus-1.0/dbus-daemon-launch-helper
blacklist /usr/lib/eject/dmcrypt-get-device
blacklist /usr/lib/openssh
blacklist /usr/lib/opera/opera_sandbox
blacklist /usr/lib/policykit-1/polkit-agent-helper-1
blacklist /usr/lib/squid/basic_pam_auth
blacklist /usr/lib/ssh
blacklist /usr/lib/vmware
blacklist /usr/lib/xorg/Xorg.wrap
blacklist /usr/libexec/openssh
# since firejail version 0.9.73
blacklist ${PATH}/dpkg*
blacklist ${PATH}/apt*
blacklist ${PATH}/dumpcap
blacklist ${PATH}/efibootdump
blacklist ${PATH}/efibootmgr
blacklist ${PATH}/passmass
blacklist ${PATH}/proxy
blacklist ${PATH}/aa-*
blacklist ${PATH}/airscan-discover
blacklist ${PATH}/avahi*
blacklist ${PATH}/dbus-*
blacklist ${PATH}/debconf*
blacklist ${PATH}/grub-*
blacklist ${PATH}/kernel-install  # from systemd package

# binaries installed by firejail
blacklist ${PATH}/firemon
blacklist ${PATH}/firecfg
blacklist ${PATH}/jailcheck
blacklist ${PATH}/firetools

# other SUID binaries
blacklist /opt/microsoft/msedge*/msedge-sandbox
blacklist /usr/lib/virtualbox
blacklist /usr/lib64/virtualbox

# prevent lxterminal connecting to an existing lxterminal session
blacklist /tmp/.lxterminal-socket*
# prevent tmux connecting to an existing session
blacklist /tmp/tmux-*

# disable terminals running as server resulting in sandbox escape
blacklist ${PATH}/foot
blacklist ${PATH}/footserver
blacklist ${PATH}/gnome-terminal
blacklist ${PATH}/gnome-terminal.wrapper
blacklist ${PATH}/kgx
# konsole doesn't seem to have this problem - last tested on Ubuntu 16.04
#blacklist ${PATH}/konsole
blacklist ${PATH}/lilyterm
blacklist ${PATH}/lxterminal
blacklist ${PATH}/mate-terminal
blacklist ${PATH}/mate-terminal.wrapper
blacklist ${PATH}/pantheon-terminal
blacklist ${PATH}/roxterm
blacklist ${PATH}/roxterm-config
blacklist ${PATH}/terminix
blacklist ${PATH}/tilix
blacklist ${PATH}/urxvtc
blacklist ${PATH}/urxvtcd
blacklist ${PATH}/xfce4-terminal
blacklist ${PATH}/xfce4-terminal.wrapper

# kernel files
blacklist /initrd*
blacklist /vmlinuz*

# snapshot files
blacklist /.snapshots

# flatpak
# most of the time bwrap is SUID binary
#blacklist ${PATH}/bwrap
blacklist ${RUNUSER}/.dbus-proxy
blacklist ${RUNUSER}/.flatpak
blacklist ${RUNUSER}/.flatpak-cache
blacklist ${RUNUSER}/.flatpak-helper
blacklist ${RUNUSER}/app
blacklist ${RUNUSER}/doc
blacklist /usr/share/flatpak
noblacklist /var/lib/flatpak/exports
blacklist /var/lib/flatpak/*

# snap
blacklist ${PATH}/snap
blacklist ${PATH}/snapctl
blacklist ${RUNUSER}/snapd-session-agent.socket
blacklist /snap
blacklist /usr/lib/snapd
blacklist /var/lib/snapd
blacklist /var/snap

# bubblejail

# mail directories used by mutt

# kernel configuration - keep this here although it's also in disable-proc.inc
blacklist /proc/config.gz

# prevent DNS malware attempting to communicate with the server using regular DNS tools
blacklist ${PATH}/delv
blacklist ${PATH}/dig
blacklist ${PATH}/dlint
blacklist ${PATH}/dns2tcp
blacklist ${PATH}/dnssec-*
blacklist ${PATH}/dnstap-read
blacklist ${PATH}/mdig
blacklist ${PATH}/dnswalk
blacklist ${PATH}/drill
blacklist ${PATH}/host
blacklist ${PATH}/iodine
blacklist ${PATH}/kdig
blacklist ${PATH}/khost
blacklist ${PATH}/knsupdate
blacklist ${PATH}/ldns-*
blacklist ${PATH}/ldnsd
blacklist ${PATH}/nslookup
blacklist ${PATH}/nsupdate
blacklist ${PATH}/nstat
blacklist ${PATH}/resolvectl
blacklist ${PATH}/unbound-host

# prevent an intruder to guess passwords using regular network tools
blacklist ${PATH}/ftp
blacklist ${PATH}/ssh*
blacklist ${PATH}/telnet

# rest of ${RUNUSER}
blacklist ${RUNUSER}/*.lock
blacklist ${RUNUSER}/inaccessible
blacklist ${RUNUSER}/pk-debconf-socket
blacklist ${RUNUSER}/update-notifier.pid


private .
protocol unix,inet,inet6
caps.drop all
seccomp
noroot
nonewprivs
private-dev
restrict-namespaces