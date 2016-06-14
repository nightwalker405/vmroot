#!/bin/sh

mkdir -p build/initrd/bin
HOSTNAME="$(hostname)"
BASE="$PWD"
USER=$(id -nu)
cat > build/initrd/sudoers <<EOF
Defaults !authenticate

%sudo ALL=(ALL:ALL) ALL
$USER ALL=(ALL:ALL) ALL
root ALL=(ALL:ALL) ALL
EOF
cat > build/initrd/init <<EOF
#!/bin/sh
busybox mount -t 9p -o trans=virtio rootdev /mnt
busybox mount -t tmpfs tmpfs /mnt/run
busybox mount -t tmpfs tmpfs /mnt/tmp
busybox mount -t proc proc /mnt/proc
busybox mount -t sysfs sys /mnt/sys
busybox mount -t devtmpfs devtmpfs /mnt/dev
mkdir /mnt/dev/pts
busybox mount -t devpts devpts /mnt/dev/pts
busybox hostname $HOSTNAME
busybox mount -o bind "/sudoers" "/mnt/etc/sudoers"
busybox chown 0:0 /mnt/etc/sudoers
busybox chmod 600 /mnt/etc/sudoers
busybox chroot /mnt dhclient eth0
busybox chroot /mnt sh -c 'echo nameserver 8.8.8.8 > /etc/resolv.conf'
busybox chroot /mnt update-binfmts --enable
busybox chroot /mnt /usr/bin/script /dev/null -q -c 'sudo -u $USER -i env HADES_PROFILE=vmroot zsh'
echo 'Shutdown!'
echo o > /mnt/proc/sysrq-trigger
EOF
chmod +x build/initrd/init
mkdir -p build/initrd/mnt
cp /bin/busybox build/initrd/bin
ln -sf /bin/busybox build/initrd/bin/sh

(cd build/initrd/ && find . | cpio -H newc -o > ../initrd.img 2>/dev/null)

qemu-system-x86_64 -enable-kvm -kernel deps/vmlinuz-4.4.13 \
  -netdev user,id=user.0 -device virtio-net-pci,netdev=user.0 \
  -initrd build/initrd.img \
  -fsdev local,id=rootdev,path=/,security_model=none \
  -device virtio-9p-pci,fsdev=rootdev,mount_tag=rootdev \
  -append 'quiet init=/bin/sh console=ttyS0' -nographic \
  -device virtio-rng-pci \
  -m 2048

#  -append 'root=rootdev ro rootfstype=9p rootflags=trans=virtio init=/bin/sh console=ttyS0' -nographic
#  -display curses
#  -initrd "/boot/initrd.img-$(uname -r)" \
