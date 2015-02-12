<!-- -*- markdown -*- -->
# ExtFuse

## Present Your Archives by Extension

ExtFuse is a FUSE (Filesystem in Userspace) module that presents a directory tree in a different form: by extension, rather than by directory structure.  So you can mount some backup and browse all your `.mp3` files, wherever they may be in the tree, or all the `.txt` files. It's much like some uses of the `find` command, but presented as directories instead of as a list of filenames (or perhaps like using `**` with bash's `globstar` option, only cached).

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

	$ extfs.py -o path=/path/to/top /home/me/mnt
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

And in fact the directory tree under `/home/me/mnt/` would look like this:

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
			otherproject_11.pyc -> /path/to/top/second/otherproject.pyc
		sh/
			run_12.sh -> /path/to/top/first/run.sh
		txt/
			README_13.txt -> /path/to/top/README.txt
			README_14.txt -> /path/to/top/first/README.txt
			info_15.txt -> /path/to/top/first/info.txt

You get the idea.  Each file in the directories is a symbolic link to the real file that it represents.  Note that the fact that there are multiple files with the same name (`README.txt`) is not a problem, and that each file is suffixed with a unique number, after which its extension is tacked on to make handling simpler for programs that look at extensions.  Files with no extension (or empty extensions, i.e. that end in '`.`') are in the special "`_.`" directory (this cannot be a real extension of any file, as it contains a period).  An initial period does not count as delimiting an extension, so "`.gitignore`" winds up with the other "no-extension" files.  If there are multiple periods in a filename, only the last counts for determining the extension (so `.tar.gz` files would get grouped with other `.gz` files.)

The filesystem is (currently) read-only and static.  You can change the files through their symlinks, but you can't create new files in the extension file-system, and new files created in the underlying tree are *not* reflected automatically in the extension file-system. You have to unmount and remount.

# How it Works

Upon mounting a directory tree, ExtFs walks through it and visits all the regular files, and stores them in a SQLite database (by default, a temporary file).  Then it simply consults the database to present the directory of extensions and the links as needed.

Of course, this leads to important limitations and shortcomings. Because the database is never updated, the extension file-system is a static snapshot, as was mentioned above, and does not reflect changes. Also, you have to have someplace to put the database file.  If the tree is large, it may take a little while to build the database and also to access it.  At the moment, ExtFs also writes a debug file in "`DBG`", which can't be completely disabled from the options.

Since it's really just a presentation of the list of files, it isn't necessary for ExtFs to walk the tree itself: you can give it a list of files you create by other ways (e.g. the `find` command), which can be more discriminating, using exclusion rules and so forth, rather than using its simple built-in walker.  Give the name of the file containing the list of files (one per line) as the `filelist` mount option.  If the `filelist` option is given no value, or a value of '`-`', then ExtFs will read from standard input.  If the `zeroterm` mount option is present, the filenames should be terminated by null characters (as might be produced by the `-print0` option of GNU `find`) instead of newlines.  This will let you handle filenames with embedded newlines or trailing whitespace, both of which will fail in an ordinary file list.

So you can do:

	$ find "$PWD" -path "$PWD"/.git -prune -o -type f -print0 | extfs.py -o filelist=-,zeroterm /mnt/point

to skip the `.git` subtree of your current directory, or use multiple invocations of `find` to combine several unrelated trees into a single filelist for mounting.

# Usage and Options

ExtFs works like a normal FUSE module, taking mount options with "`-o`". You need to give it "`-o path=/path/to/root`" to tell it what tree to parse.  You should use a fully-qualified path, or the symbolic links will be relative and will probably point to the wrong place.  You can also specify "`dbfile=/path/DatabaseFile.db`" to move the database file from its default temporary file.  This can be handy if you have a large archive that isn't changing much: you can build the database file once and save it, then use the dbfile option and the "`noscan`" option to tell it to use the database file as it is rather than actually walk the tree and rebuild it.  You will also need to use the `noclean` option on the first mounting to tell ExtFs not to remove the database file when the extension file-system is unmounted.

If the `dbfile` option is set to a directory, ExtFs will (attempt to) create a temporary file in that directory.  By default, it goes wherever passes for "temporary"; generally `/tmp`.

So you can do

	$ extfs.py -o path=/big/archive/place,dbfile=/special/DB/place.db,noclean /mntpt

to build the table, and then later use

	$ extfs.py -o path=/big/archive/place,dbfile=/special/DB/place.db,noscan,noclean /mntpt

to mount it without rebuilding the database.

The `verbose` option just prints out a progress line for every 1000 files scanned when building the database.

To unmount, use "`fusermount -u /mount/point`"

# Prefix Mode

Once we have the database, we can of course present it any number of ways.  Now you can use "prefix-mode" to view the files by prefix (sort of) instead of by extension.  Give the `prefix` option at mount time, and the behavior is different.  For one thing, `ls /mnt/point/` no longer shows you the list of extension directories.  In fact, it doesn't show you anything at all!  This is on purpose, though not necessarily the best thing to do in this situation.  The subdirectories only exist if you go looking for them.  So if you say `ls /mnt/point/e/`, you will get a list of soft links to all the files whose names begin with "e" (or "E"; SQLite's "LIKE" is case-insensitive, at least by default on my machine.  It apparently depends on certain SQLite extensions).  If you look at `/mnt/point/ex/` you will find links to all the files that begin with "ex", and so forth.  This, too, is a lot like using a * wildcard; `ls /mnt/point/foo/` is a lot like `ls foo*`, only it descends directories.   It would be like `ls **/foo*` with bash `globstar` active, except that it would also catch things at the top level, which the glob would not.

# Bugs and TODO

* Does not handle non-ascii filenames, at least not with built-in directory scan.
* What about files that start/end with *two* periods? Do we handle those okay?
* Lots of cleanup and debug removal.
* Control case-(in)sensitivity in SQLite.
* Other modes/ways to present?  Maybe some better coding for them, better refactoring of things.
* (Optionally?) stat files upon reading so as to provide correct dates.
	* Is this really useful?  `ls -lL` does it already.
* Better error handling.
* Perhaps eventually use pyinotify to make the filesystem updating.
