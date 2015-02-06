#!/usr/bin/env python
from fuse import Fuse, Stat
import fuse
import os
import path
import sys
import stat
import errno
import tempfile
try:
    import sqlite
except ImportError:
    import sqlite3 as sqlite
from itertools import count

def debugfunc(f):
    def newf(*args, **kwargs):
        ExtFuse.DBG(">>entering function %s(%s)"%(f.__name__, str(args)))
        x=f(*args, **kwargs)
        ExtFuse.DBG("<<leaving function %s, returning %s"%
                    (f.__name__, str(x)))
        return x
    return newf

def escape_for_sql(string):
    x=string
    if isinstance(string,unicode):
        x=string.encode('utf-8')
    x=x.replace("'","''")
    return x

fuse.fuse_python_api=(0,2)

def getParts(path):
    """
    Return the slash-separated parts of a given path as a list
    """
    if path == os.sep:
        return [os.sep]
    else:
        return path.split(os.sep)

def readZeroes(fh):
    while True:
        buf=''
        ch=fh.read(1)
        while ch != "\0":
            if not ch:
                return
            buf += ch
            ch=fh.read(1)
        yield buf

class ExtFuse(Fuse):

    dbg=open("DBG","w")
    DEBUG=True

    tablecommand="""CREATE TABLE files (_id int primary key,
	fullpath varchar(1000) UNIQUE,
	newname varchar(1000),
	ext varchar(1000));"""
    indexcommands=["""CREATE INDEX Exts ON files (ext);""",
                   """CREATE INDEX Names ON files (newname);"""]
    insertcommand="""INSERT INTO files VALUES ({0}, '{1}', '{2}_{0}', '{3}');"""

    # Dummy extension for the extensionless.  Should contain a period.
    NULLEXT='_.'
    # Extended version:
    ENULLEXT='.'+NULLEXT

    @classmethod
    def DBG(cls, s):
        if not cls.DEBUG:
            return
        try:
            cls.dbg.write(s+"\n")
            cls.dbg.flush()
        except Exception as e:
            pass

    def __init__(self, *args, **kw):
        self.already=False
        Fuse.__init__(self, *args, **kw)

    def namekey(self, path):
        # Returns the new name, stripping off extension or NULLEXT
        name=path.rsplit(os.path.sep, 1)[-1]
        if name[-3:] == self.ENULLEXT: # Probably don't need this check anymore.
            return name[:-3]
        namekey, ext=os.path.splitext(name)
        return namekey

    @debugfunc
    def recordfile(self, fil):
        name = fil.rsplit(os.path.sep,1)[-1]
        base, ext = os.path.splitext(name)
        base=escape_for_sql(base)
        ext=escape_for_sql(ext)
        fil=escape_for_sql(fil)
        if not ext or len(ext)<2:
            ext=self.ENULLEXT
        ext=ext[1:]
        cmd=self.insertcommand.format(next(self.counter), fil, base, ext)
        # print cmd;
        self.cursor.execute(cmd)

    @debugfunc
    def scanfs(self):
        self.cursor.execute(self.tablecommand)
        for cmd in self.indexcommands:
            self.cursor.execute(cmd)
        self.pathobj=path.path(self.path)
        count=0
        w=self.pathobj.walkfiles(errors='warn')
        for fil in w:
            if hasattr(self,'debug'):
                self.DBG("-- walking: {0}".format(fil))
            self.recordfile(fil)
            count+=1
            if hasattr(self, 'verbose') and not count%1000:
                print "... "+str(count)
        self.connection.commit()
        if hasattr(self,'debug'):
            self.cursor.execute("SELECT * FROM files;")
            for l in self.cursor:
                print repr(l)
        return

    @debugfunc
    def scanfile(self):
        self.cursor.execute(self.tablecommand)
        for cmd in self.indexcommands:
            self.cursor.execute(cmd)
        if not self.filelist or self.filelist == '-':
            inp=sys.stdin
        else:
            inp=open(self.filelist,'r')
        if hasattr(self, 'zeroterm'):
            inp=readZeroes(inp)
        for line in inp:
            self.DBG("Read: ({0})".format(line))
            self.recordfile(line.strip())
        inp.close()
        self.connection.commit()

    @debugfunc
    def fsinit(self):
        # Idempotent!
        if self.already:
            return
        self.already=True
        self.multithreaded=False # THIS can make it work!
        try:                     # if dbfile is a dir, make a temp file there.
            st=None
            if self.dbfile:
                st=os.stat(self.dbfile)
            if not st or st.st_mode & stat.S_IFDIR:
                # os.tempnam gives warnings...
                fd, self.dbfile=tempfile.mkstemp(suffix='.db',
                                                 prefix="ExtFs",
                                                 dir=self.dbfile)
                os.close(fd)    # Don't need this.
        except OSError:
            pass
        if not hasattr(self,'noscan'):
            try:
                os.unlink(self.dbfile)
            except OSError:
                pass
        try:
            self.connection=sqlite.connect(self.dbfile)
        except sqlite.OperationalError as e:
            print "Error: %s"%str(e)
            exit(50)            # ?
        self.DBG("Opened db file %s"%self.dbfile)
        self.cursor=self.connection.cursor()
        self.counter=count()
        if hasattr(self,'noscan'):
            return
        elif hasattr(self,'filelist'):
            self.scanfile()
        else:
            self.scanfs()

    @debugfunc
    def fsdestroy(self):
        self.cursor.close()
        self.connection.close()
        if not hasattr(self, 'noclean'):
            try:
                os.unlink(self.dbfile)
            except Exception:
                pass
        return

    @debugfunc
    def is_root(self, path=None, pathelts=None):
        if pathelts is None:
            pathelts=getParts(path)[1:]
        return (path==os.sep or len(pathelts)==0 or
                pathelts == ['/'])

    # Depth is exactly two, after all.
    @debugfunc
    def is_directory(self, path=None, pathelts=None):
        if not pathelts:
            pathelts=getParts(path)[1:]
        return len(pathelts) < 1

    @debugfunc
    def getattr(self, path):
        st=Stat()
        pe=getParts(path)
        st.st_mode = stat.S_IFDIR | 0555
        st.st_ino = 0
        st.st_dev = 0
        st.st_nlink = 2
        st.st_uid = 0
        st.st_gid = 0
        st.st_size = 4096
        st.st_atime = 0
        st.st_mtime = 0
        st.st_ctime = 0
        if self.is_root(pathelts=pe):
            return st
        if len(pe)<3:          # ext dir
            query="SELECT COUNT(*) FROM files WHERE ext='{0}';".format(escape_for_sql(pe[-1]))
            try:
                self.DBG(query)
                self.cursor.execute(query)
                cnt=self.cursor.fetchone()
            except Exception as e:
                self.DBG("Whoa, except: {0}".format(str(e)))
                cnt=[0]
            if cnt[0]<1:
                self.DBG("Nothing returned, ENOENT")
                return -fuse.ENOENT
            return st
        else:
            st.st_mode=stat.S_IFLNK | 0777
            st.st_nlink=1
            st.st_size=0
            newname=self.namekey(pe[-1])
            # I guess I should search on the name and not _id, so that
            # using dummy names with real _ids won't work.
            query="SELECT COUNT(*) FROM files WHERE newname='{0}';".format(escape_for_sql(newname))
            try:
                self.DBG(query)
                self.cursor.execute(query)
                cnt=self.cursor.fetchone()
            except Exception as e:
                self.DBG("Whoa, except: {0}".format(e))
                cnt=[0]
            if cnt[0]<1:
                self.DBG("File not found.")
                return -fuse.ENOENT
        return st

    @debugfunc
    def readlink(self, filename):
        namekey=self.namekey(filename)
        base, uniq=namekey.rsplit('_',1)
        if not uniq:
            return -fuse.ENOENT
        try:
            query="SELECT fullpath FROM files WHERE _id={0}".format(int(uniq))
        except ValueError:
            return -fuse.ENOENT
        self.DBG(query)
        self.cursor.execute(query)
        path=self.cursor.fetchone()
        if not path or not path[0]:
            return -fuse.ENOENT
        return str(path[0].encode('utf-8'))

    @debugfunc
    def readdir(self, path, offset):
        dirents=[]
        yield fuse.Direntry('.') # These are constant.
        yield fuse.Direntry('..')
        pe=getParts(path)[1:]
        if self.is_root(path=path):
            # Return extension directories
            query="SELECT DISTINCT ext FROM files;"
            self.DBG(query)
            self.cursor.execute(query)
            l=self.cursor.fetchall()
            self.DBG("== {0}".format(str(l)))
            dirents.extend([x[0] for x in l])
            self.DBG("readdir returning {0}".format(str(dirents)))
            for r in dirents:
                self.DBG("readdir yielding {0}".format(str(r)))
                try:
                    if not r:
                        # Should never be empty string, but...
                        # yield fuse.Direntry('?.ERROR')
                        continue
                    yield fuse.Direntry(r.encode('utf-8'))
                except Exception as e:
                    self.DBG("Whoa, exception {0}".format(str(e)))
        elif len(pe)==1:
            query="SELECT newname FROM files WHERE ext='{0}';".format(escape_for_sql(pe[0]))
            self.DBG(query)
            self.cursor.execute(query)
            l=self.cursor.fetchone()
            while l:
		try:
                   self.DBG("File: {0}".format(str(l)))
                   if pe[0] == self.NULLEXT:
                       yield fuse.Direntry(str(l[0]))
                   else:
                       yield fuse.Direntry("{0}.{1}".format(l[0],pe[0]))
		except Exception as e:
		    self.DBG("Whoa, exception: {0}".format(str(e)))
                l=self.cursor.fetchone()
        else:
            raise StopIteration

    def mknod(self, path, mode, dev):
        return -fuse.EROFS

    def unlink(self, path):
        # RO filesystem
        return -fuse.EROFS

    def write(self, path, buf, offset):
        return -fuse.EROFS

    def read(self, path, size, offset):
        return ''               # No need, really; it's all symlinks.

    def mkdir(self, path, mode):
        return -fuse.EROFS

    def release(self, path, flags):
        return 0

    def open(self, path, flags):
        return 0

    def truncate(self, path, size):
        return 0

    def utime(self, path, times):
        return 0

    def symlink(self, *args):
        return -fuse.EROFS

    def link(self, *args):
        return -fuse.EROFS

    def rmdir(self, *args):
        return -fuse.EROFS

    def chmod(self, *args):
        return -fuse.EROFS

server=ExtFuse(version="%prog "+fuse.__version__,
               usage='', dash_s_do='setsingle')
server.path=os.getenv('PWD')
server.dbfile=None
server.parser.add_option(mountopt='path')
server.parser.add_option(mountopt='filelist')
server.parser.add_option(mountopt='zeroterm')
server.parser.add_option(mountopt='dbfile')
server.parser.add_option(mountopt='noscan')
server.parser.add_option(mountopt='noclean')
server.parser.add_option(mountopt='verbose')
server.parser.add_option(mountopt='debug')
server.parse(errex=1, values=server)
#try:
server.fsinit()
#except Exception as e:
#    print str(e)

# crs=server.connection.cursor()
# crs.execute("SELECT * FROM files;")
# l=crs.fetchone()
# while (l):
#     print str(l)
#     l=crs.fetchone()

print "Ready."
server.main()
