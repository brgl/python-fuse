#!/usr/bin/env python

#    Copyright (C) 2001  Jeff Epler  <jepler@unpythonic.dhs.org>
#    Copyright (C) 2006  Csaba Henk  <csaba.henk@creo.hu> 
#
#    This program can be distributed under the terms of the GNU LGPL.
#    See the file COPYING.
#

import os, sys
from errno import *
from stat import *
# some spaghetti to make it usable without fuse-py being installed
for i in True, False:
    try:
        import fuse
        from fuse import Fuse
    except ImportError:
        if i:
            try:
                import _find_fuse_parts
            except ImportError:
                pass
        else:
            raise


if not hasattr(fuse, '__version__'):
    raise RuntimeError, \
        "your fuse-py doesn't know of fuse.__version__, probably it's too old."


fuse.feature_assert('stateful_files')


def flag2mode(flags):
    md = {os.O_RDONLY: 'r', os.O_WRONLY: 'w', os.O_RDWR: 'w+'}
    m = md[flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)]

    if flags | os.O_APPEND:
        m = m.replace('w', 'a', 1)

    return m


class Xmp(Fuse):

    root = '/'

    def __init__(self, *args, **kw):

        Fuse.__init__(self, *args, **kw)

        # do stuff to set up your filesystem here, if you want
        #import thread
        #thread.start_new_thread(self.mythread, ())
        pass

#    def mythread(self):
#
#        """
#        The beauty of the FUSE python implementation is that with the python interp
#        running in foreground, you can have threads
#        """
#        print "mythread: started"
#        while 1:
#            time.sleep(120)
#            print "mythread: ticking"

    def getattr(self, path):
        return os.lstat(self.root + path)

    def readlink(self, path):
        return os.readlink(self.root + path)

    def readdir(self, path, offset):
        for e in os.listdir(self.root + path):
            yield fuse.Direntry(e)

    def unlink(self, path):
        os.unlink(self.root + path)

    def rmdir(self, path):
        os.rmdir(self.root + path)

    def symlink(self, path, path1):
        os.symlink(path, self.root + path1)

    def rename(self, path, path1):
        os.rename(self.root + path, self.root + path1)

    def link(self, path, path1):
        os.link(self.root + path, self.root + path1)

    def chmod(self, path, mode):
        os.chmod(self.root + path, mode)

    def chown(self, path, user, group):
        os.chown(self.root + path, user, group)

    def truncate(self, path, len):
        f = open(self.root + path, "a")
        f.truncate(len)
        f.close()

    def mknod(self, path, mode, dev):
        os.mknod(self.root + path, mode, dev)

    def mkdir(self, path, mode):
        os.mkdir(self.root + path, mode)

    def utime(self, path, times):
        os.utime(self.root + path, times)

    def access(self, path, mode):
        if not os.access(self.root + path, mode):
            return -EACCES

#    This is how we could add stub extended attribute handlers...
#    (We can't have ones which aptly delegate requests to the underlying fs
#    because Python lacks a standard xattr interface.)
#
#    def getxattr(self, path, name, size):
#        val = name.swapcase() + '@' + path
#        if size == 0:
#            # We are asked for size of the value.
#            return len(val)
#        return val
#
#    def listxattr(self, path, size):
#        # We use the "user" namespace to please XFS utils
#        aa = ["user." + a for a in ("foo", "bar")]
#        if size == 0:
#            # We are asked for size of the attr list, ie. joint size of attrs
#            # plus null separators.
#            return len("".join(aa)) + len(aa)
#        return aa

    def statfs(self):
        """
        Should return an object with statvfs attributes (f_bsize, f_frsize...).
        Eg., the return value of os.statvfs() is such a thing (since py 2.2).
        If you are not reusing an existing statvfs object, start with
        fuse.StatVFS(), and define the attributes.

        To provide usable information (ie., you want sensible df(1)
        output, you are suggested to specify the following attributes:

            - f_bsize - preferred size of file blocks, in bytes
            - f_frsize - fundamental size of file blcoks, in bytes
                [if you have no idea, use the same as blocksize]
            - f_blocks - total number of blocks in the filesystem
            - f_bfree - number of free blocks
            - f_files - total number of file inodes
            - f_ffree - nunber of free file inodes
        """

        return os.statvfs(self.root)

    def main(self, *a, **kw):

        # Define the file class locally as that seems to be the easiest way to
        # inject instance specific data into it...

        server = self

        class XmpFile:

            def __init__(self, path, flags, *mode):
                self.file = os.fdopen(os.open(server.root + path, flags, *mode),
                                      flag2mode(flags))
                self.fd = self.file.fileno()

            def read(self, length, offset):
                self.file.seek(offset)
                return self.file.read(length)

            def write(self, buf, offset):
                self.file.seek(offset)
                self.file.write(buf)
                return len(buf)

            def release(self, flags):
                self.file.close()

            def fsync(self, isfsyncfile):
                if isfsyncfile and hasattr(os, 'fdatasync'):
                    os.fdatasync(self.fd)
                else:
                    os.fsync(self.fd)

            def flush(self):
                self.file.flush()
                # cf. xmp_flush() in fusexmp_fh.c
                os.close(os.dup(self.fd))

            def fgetattr(self):
                return os.fstat(self.fd)

            def ftruncate(self, len):
                self.file.truncate(len)

        self.file_class = XmpFile

        return Fuse.main(self, *a, **kw)


def main():

    usage = """
Userspace nullfs-alike: mirror the filesystem tree from some point on.

""" + Fuse.fusage

    server = Xmp(version="%prog " + fuse.__version__,
                 usage=usage,
                 dash_s_do='setsingle',
                 fetch_mp=True)

    server.parser.add_option(mountopt="root", metavar="PATH", default='/', type=str,
                             help="mirror filesystem from under PATH [default: %default]")
    server.parse(values=server, errex=1)

    try:
        if server.fuse_args.mount_expected():
            os.stat(server.root)
    except OSError:
        print >> sys.stderr, "can't stat root of underlying filesystem"
        sys.exit(1)

    server.main()


if __name__ == '__main__':
    main()