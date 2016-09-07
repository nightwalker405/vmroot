#!/usr/bin/python3
import os, argparse, binascii, subprocess, hashlib, tempfile, pwd, atexit, shutil, platform


## universal cached downloader

def download(url, checksum):
    cache_dir = os.environ.get('XDG_CACHE_DIR', os.path.expanduser('~/.cache'))
    dl_dir = cache_dir + '/downloads/'

    try: os.makedirs(dl_dir)
    except OSError: pass

    target_path = dl_dir + checksum
    tmp_path = dl_dir + 'tmp:' + binascii.hexlify(os.urandom(16))

    if os.path.exists(target_path):
        return target_path

    subprocess.check_call([
        'wget', url, '-O', tmp_path
    ])

    checksum_type, checksum_hex = checksum.split(':')

    digest = hashlib.new(checksum_type)
    with open(tmp_path, 'rb') as f:
        while True:
            b = f.read(1024 * 32)
            if not b: break
            digest.update(b)

    if digest.hexdigest() != checksum_hex:
        raise Exception('download (%r) integrity error' % url)

    os.rename(tmp_path, target_path)

    return target_path

##

def write_file(path, data):
    with open(path, 'w') as f:
        f.write(data)

def make_initrd():
    user = pwd.getpwuid(os.getuid()).pw_name
    dir = tempfile.mkdtemp()
    os.mkdir(dir + '/initrd')
    atexit.register(shutil.rmtree, dir)
    write_file(dir + '/initrd/sudoers',
               '''Defaults !authenticate
%sudo ALL=(ALL:ALL) ALL
{user} ALL=(ALL:ALL) ALL
root ALL=(ALL:ALL) ALL'''.format(user=user))

    os.mkdir(dir + '/initrd/bin')
    os.mkdir(dir + '/initrd/mnt')

    shutil.copy('/bin/busybox', dir + '/initrd/bin/busybox')
    os.symlink('/bin/busybox', dir + '/initrd/bin/sh')

    write_file(dir + '/initrd/init',
'''#!/bin/sh
export HOME=/home/{user}

busybox mount -t 9p -o trans=virtio,version=9p2000.L rootdev /mnt
busybox mount -t tmpfs tmpfs /mnt/run
busybox mount -t tmpfs tmpfs /mnt/tmp
busybox mount -t proc proc /mnt/proc
busybox mount -t sysfs sys /mnt/sys
busybox mount -t devtmpfs devtmpfs /mnt/dev
mkdir /mnt/dev/pts
busybox mount -t devpts devpts /mnt/dev/pts
busybox hostname {hostname}
busybox mount -o bind "/sudoers" "/mnt/etc/sudoers"
busybox chown 0:0 /mnt/etc/sudoers
busybox chmod 600 /mnt/etc/sudoers
busybox chroot /mnt dhclient eth0
mkdir -p /mnt/run/resolvconf
busybox chroot /mnt sh -c 'echo nameserver 8.8.8.8 > /etc/resolv.conf'
busybox chroot /mnt update-binfmts --enable
busybox chroot /mnt /usr/bin/script /dev/null -q -c 'HADES_PROFILE=vmroot bash'
echo 'Shutdown!'
echo o > /mnt/proc/sysrq-trigger
sleep 999
'''.format(hostname=platform.node(), user=user))
    os.chmod(dir + '/initrd/init', 0o755)
    os.mkdir(dir + '/mnt')

    subprocess.check_call(
        'find . | cpio -H newc -o > ../initrd.img 2>/dev/null',
        shell=True,
        cwd=dir + '/initrd'
    )

    return dir + '/initrd.img'

def run(ns):
    initrd = make_initrd()
    # https://cdn.atomshare.net/42d5ef87e9581472ecfa304f2a3e4c3f18728dba/.config
    kernel = download('https://cdn.atomshare.net/8d99742552a6b2730aaccd15df10ca5b3e5281d5/vmlinuz-4.4.20', 'sha1:8d99742552a6b2730aaccd15df10ca5b3e5281d5')

    cmd = ['qemu-system-x86_64',
           '-enable-kvm', '-kernel', kernel, '-initrd', initrd,
           '-device', 'virtio-net-pci,netdev=eth0',

           '-fsdev', 'local,id=rootdev,path=/,security_model=none',
           '-device', 'virtio-9p-pci,fsdev=rootdev,mount_tag=rootdev,disable-legacy=false',

           '-append', 'quiet init=/bin/sh console=ttyS0',
           '-nographic',
           '-device', 'virtio-rng-pci',

           '-m', '2048']

    # user mode networking
    cmd += ['-netdev', 'user,id=eth0']

    subprocess.call(cmd)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--forward', metavar='[tcp/udp]:HOST:GUEST', help='Forwards port HOST to GUEST.')
    parser.add_argument('cmd', nargs='*', help='Run command.')
    run(parser.parse_args())
