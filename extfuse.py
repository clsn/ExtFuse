#!/usr/bin/env python
from fuse import Fuse, Stat
import fuse
import os
import path
import sys
import stat
import errno
try:
    import sqlite
except ImportError:
    import sqlite3 as sqlite

def debugfunc(f):
    def newf(*args, **kwargs):
        ExtFuse.dbg.write(">>entering function %s(%s)\n"%(f.__name__, str(args)))
        ExtFuse.dbg.flush()
        x=f(*args, **kwargs)
        ExtFuse.dbg.write("<<leaving function %s, returning %s\n"%
                          (f.__name__, str(x)))
        ExtFuse.dbg.flush()
        return x
    return newf

def mod(self):
    return "(stat mode={0})".format(self.st_mode)
Stat.__str__=mod

def escape_for_sql(string):
    x=string
    x=x.replace("'","''")
    return x

def unescape_from_sql(string):
    return string.replace("''","'")

fuse.fuse_python_api=(0,2)

def getDepth(path):
    """
    Return the depth of a given path, zero-based from root ('/')
    """
    if path == os.sep:
        return 0
    else:
        return path.count(os.sep)

def getParts(path):
    """
    Return the slash-separated parts of a given path as a list
    """
    if path == os.sep:
        return [os.sep]
    else:
        return path.split(os.sep)

class ExtFuse(Fuse):

    dbg=open("DBG","w")

    tablecommand="""CREATE TABLE files (_id int primary key,
	fullpath varchar(1000) UNIQUE,
	newname varchar(1000),
	ext varchar(1000));"""
    indexcommands=["""CREATE INDEX Exts ON files (ext);""",
                   """CREATE INDEX Names ON files (newname);"""]
    insertcommand="""INSERT INTO files VALUES ({0}, '{1}', '{2}_{0}', '{3}');"""

    def DBG(self, s):
        self.dbg.write(s+"\n")
        self.dbg.flush()

    def __init__(self, *args, **kw):
        Fuse.__init__(self, *args, **kw)

    already=False
    @debugfunc
    def fsinit(self):
        # Idempotent!
        if self.already:
            return
        self.already=True
        # self.dbfile=os.tmpnam()
        self.dbfile="/home/mark/EXTFS.db"
        try:
            os.unlink(self.dbfile)
        except OSError:
            pass
        self.multithreaded=False # THIS can make it work!
        self.connection=sqlite.connect(self.dbfile)
        self.cursor=self.connection.cursor()
        self.cursor.execute(self.tablecommand)
        for cmd in self.indexcommands:
            self.cursor.execute(cmd)
        self.pathobj=path.path(self.path)
        count=0
        w=self.pathobj.walkfiles()
        for fil in w:
            direc, name = fil.rsplit(os.path.sep,1)
            base, ext = os.path.splitext(name)
            # self.DBG("Base({0}), Ext({1})".format(base,ext))
            base=base.replace('\\', '\\\\')
            base=base.replace("'", "\\'")
            ext=ext.replace('\\', '\\\\')
            ext=ext.replace("'", "\\'")
            if not ext:
                ext='._'
            ext=ext[1:]
            cmd=self.insertcommand.format(count, fil, base, ext)
            print cmd;
            rv=self.cursor.execute(cmd)
            count+=1
        self.connection.commit()
        self.connection.close() # ?
        self.connection=sqlite.connect(self.dbfile)
        self.cursor=self.connection.cursor()
#        self.cursor.execute("SELECT * FROM files;")
#        for l in self.cursor:
#            print str(l)

    @debugfunc
    def fsdestroy(self):
        self.cursor.close()
        self.connection.close()

    @debugfunc
    def is_root(self, path=None, pathelts=None):
        if pathelts is None:
            pathelts=getParts(path)[1:]
        self.DBG("is_root ({0}), ({1})".format(str(path), str(pathelts)))
        return (path==os.sep or len(pathelts)==0 or
                pathelts == ['/'])

    # Depth is exactly two, after all.
    @debugfunc
    def is_directory(self, path=None, pathelts=None):
        if not pathelts:
            pathelts=getParts(path)[1:]
        return len(pathelts) < 1

    @debugfunc
    def _getattr(self, path):
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
        self.DBG("getattr pe: {0}".format(str(pe)))
        if self.is_root(pathelts=pe):
            return st
        if len(pe)<3:          # ext dir
            query="SELECT COUNT(*) FROM files WHERE ext='{0}';".format(escape_for_sql(pe[-1]))
            try:
                self.DBG(query)
                self.DBG("EJIIOFHSDKDH")
                rv=self.cursor.execute(query)
                self.DBG("AAAAAAAA")
                self.DBG("exec returned {0}".format(str(rv)))
                cnt=self.cursor.fetchone()
                self.DBG("Returned {0}".format(str(cnt)))
            except Exception as e:
                self.DBG("Whoa, except: {0}".format(str(e)))
                cnt=[0]
            if cnt[0]<1:
                self.DBG("Nothing returned, ENOENT")
                return -fuse.ENOENT
            return st
        else:
            # st.st_mode=stat.S_IFREG | 0444
            st.st_mode=stat.S_IFLNK | 0777
            st.st_nlink=1
            st.st_size=0        # XXXXXXX
        return st


    @debugfunc
    def readlink(self, filename):
        base, uniq=filename.rsplit('_',1)
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
        return str(path[0])

    def getattr(self, *args, **kwargs):
        try:
            return self._getattr(*args, **kwargs)
        except Exception as e:
            self.DBG("!!!, exception in getattr: {0}".format(str(e)))

    @debugfunc
    def _readdir(self, path, offset):
        dirents=['.', '..']
        pe=getParts(path)[1:]
        self.DBG("readdir pe: "+str(pe))
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
                    yield fuse.Direntry(str(r))
                except Exception as e:
                    self.DBG("Whoa, exception {0}".format(str(e)))
        elif len(pe)==1:
            query="SELECT newname FROM files WHERE ext='{0}';".format(escape_for_sql(pe[0]))
            self.DBG(query)
            self.cursor.execute(query)
            l=self.cursor.fetchone()
            while l:
                self.DBG("File: {0}".format(str(l)))
                yield fuse.Direntry(str(l[0]))
                l=self.cursor.fetchone()
        else:
            raise StopIteration

    def readdir(self, *args, **kwargs):
        try:
            return self._readdir(*args, **kwargs)
        except Exception as e:
            self.DBG("!!!, exception in readdir: {0}".format(str(e)))

    @debugfunc
    def mknod(self, path, mode, dev):
        return 0

    @debugfunc
    def unlink(self, path):
        # RO filesystem
        return 0

    @debugfunc
    def write(self, path, buf, offset):
        return 0

    @debugfunc
    def read(self, path, size, offset):
        return ''               # XXXXXXXXX

    @debugfunc
    def mkdir(self, path, mode):
        return 0

    @debugfunc
    def release(self, path, flags):
        return 0

    @debugfunc
    def open(self, path, flags):
        return 0

    @debugfunc
    def truncate(self, path, size):
        return 0

    @debugfunc
    def utime(self, path, times):
        return 0

server=ExtFuse(version="%prog "+fuse.__version__,
               usage='', dash_s_do='setsingle')
server.parser.add_option(mountopt='path', default='.')
server.parse(errex=1, values=server)
try:
    server.fsinit()
except Exception as e:
    print str(e)

crs=server.connection.cursor()
crs.execute("SELECT * FROM files;")
l=crs.fetchone()
while (l):
    print str(l)
    l=crs.fetchone()

server.main()
