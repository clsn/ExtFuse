# ExtFuse

## Present Your Archives by Extension

ExtFuse is a FUSE (Filesystem in Userspace) module that presents a directory tree in a different form: by extension, rather than by directory structure.  So you can mount some backup and browse all your .mp3 files, wherever they may be in the tree, or all the .txt files. It's much like some uses of the _find_ command, but presented as directories instead of as a list of filenames.

## Example

Say for example you had a directory tree with the following structure:

	top/
		README.txt
		explain.mp3
		first/
			.gitignore
			README.txt
			info.txt
			source.c
			source.o
			Makefile
			run.sh
			spoken.mp3
		second/
			.config.log
			otherproject.py
			otherproject.pyc
			extralib.c
			libs/
				morestuff.c
				morestuff.o
				example.mp3

After doing
	$ ./extfs -o path=/path/to/top /home/me/mnt
	Ready.
	$ cd /home/me/mnt
	$ ls -1F

You would see:
	_./
	c/
	log/
	mp3/
	o/
	py/
	pyc/
	sh/
	txt/

And in fact the directory tree under /home/me/mnt/ would look like this:

	mnt/
		_./
			.gitignore_20 -> /path/to/top/first/.gitignore
			Makefile_1 -> /path/to/top/first/Makefile
		c/
			extralib_2.c -> /path/to/top/second/extralib.c
			morestuff_3.c -> /path/to/top/second/libs/morestuff.c
			source_4.c -> /path/to/top/first/source.c
		log/
			.config_21.log -> /path/to/top/second/.config.log
		mp3/
			example_5.mp3 -> /path/to/top/second/lib/example.mp3
			explain_6.mp3 -> /path/to/top/explain.mp3
			spoken_7.mp3 -> /path/to/top/first/spoken.mp3
		o/
			morestuff_8.o -> /path/to/top/second/libs/morestuff.o
			source_9.o -> /path/to/top/first/source.o
		py/
			otherproject_10.py -> /path/to/top/second/otherproject.py
		pyc/
			otherproject_11.pyc ->/path/to/top/second/otherproject.pyc
		sh/
			run_12.sh -> /path/to/top/first/run.sh
		txt/
			README_13.txt -> /path/to/top/README.txt
			README_14.txt -> /path/to/top/first/README.txt
			info_15.txt -> /path/to/top/first/info.txt

You get the idea.  Each file in the directories is a symbolic link to the real file that it represents.  Note that the fact that there are multiple files with the same name (README.txt) is not a problem, and that each file is suffixed with a unique number, after which its extension is tacked on to make handling simpler for programs that look at extensions.  Files with no extension (or empty extensions, i.e. that end in '.') are in the special "_." directory (this cannot be a real extension of any file, as it contains a period).  An initial period does not count as delimiting an extension, so ".gitignore" winds up with the other "no-extension" files.

The filesystem is (currently) read-only and static.  You can change the files through their symlinks, but you can't create new files in the extension file-system, and new files created in the underlying tree are *not* reflected automatically in the extension file-system. You have to unmount and remount.

# How it Works

Upon mounting a directory tree, ExtFs walks through it and visits all the regular files, and stores them in a SQLite database (by default, $HOME/EXTFS.db).  Then it simply consults the database to present the directory of extensions and the links as needed.

Of course, this leads to important limitations and shortcomings. Because the database is never updated, the extension file-system is a static snapshot, as was mentioned above, and does not reflect changes. Also, you have to have someplace to put the database file.  If the tree is large, it may take a little while to build the database and also to access it.  At the moment, ExtFs also writes a debug file in "DBG", which can't be completely disabled from the options.

Since it's really just a presentation of the list of files, it shouldn't really need to walk the tree itself: you ought to be able to give it a list of files you create by other ways (e.g. the find command), which can be more discriminating, using exclusion rules and so forth.  This feature has not yet been added, but should be straightforward enough.

# Usage and Options

ExtFs works like a normal FUSE module, taking mount options with "-o". You need to give it "-o path=/path/to/root" to tell it what tree to parse.  You should use a fully-qualified path, or the symbolic links will be relative and probably point to the wrong place.  You can also specify "dbfile=/path/DatabaseFile.db" to move the database file from its default place in $HOME/EXTFS.db.  This can be handy if you have a large archive that isn't changing much: you can build the database file once and save it, then use the dbfile option and the "scan" option to tell it to use the database file as it is rather than actually walk the tree and rebuild it (use "scan=n").

So you can do

	$ extfs -o path=/big/archive/place,dbfile=/special/DB/place.db /mntpt

to build the archive, and then later use

	$ extfs -o path=/big/archive/place,dbfile=/special/DB/place.db,scan=n /mntpt

to mount it.  The "path" option should not be required here, but it probably is at the moment.

To unmount, use "fusermount -u /mount/point"

# Bugs and TODO

* Extensionless file links are broken, does not look as advertised.
* Does not handle non-ascii filenames.
* What about files that start with *two* periods?
* Should be able to handle a file list instead of a tree, in which case the path option is unnecessary.
* Path option should not be necessary if dbfile is given.
* Lots of cleanup and debug removal.
* Error handling.
* Perhaps eventually use pyinotify to make the filesystem updating.