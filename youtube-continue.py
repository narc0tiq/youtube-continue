#!/usr/bin/python
from ConfigParser import ConfigParser
import argparse, os, subprocess, glob

GLOBAL_CONF_PATH = os.path.expanduser('~/.config/youtube-continue.ini')
LOCAL_CONF_PATH = 'youtube-continue.ini'
FORMAT_ARGS = ['-o', '%(playlist_index)s-%(title)s-%(id)s.%(ext)s']

gconf = ConfigParser({'dl-args': ''})
gconf.read([GLOBAL_CONF_PATH])
if not gconf.has_section('main'):
    gconf.add_section('main')
lconf = ConfigParser({'dl-args': '', 'url': '', 'start': '1'})
lconf.read([LOCAL_CONF_PATH])
if not lconf.has_section('main'):
    lconf.add_section('main')

parser = argparse.ArgumentParser(description="Manage youtube-dl playlist directories.",
                                 epilog="""If either -G or -L are present, the URL and start index will be
                                 ignored and youtube-dl will not be called. Otherwise, the arguments passed
                                 to youtube-dl will be a merger of the -G, -L, and command-line arguments,
                                 in that order.""")
parser.add_argument('-d', '--dry-run', action='store_true', dest='dry_run',
                    help="Do not run youtube-dl, instead print the command line that would be passed to it. "
                    "Alternately, if editing configuration, print the old and new configuration values, "
                    "but do not update them.")
parser.add_argument('-u', '--url',
                    help="A URL that youtube-dl will understand as a playlist reference, "
                    "e.g. http://youtube.com/playlist?list=xxxx. Only necessary for the first run.")
parser.add_argument('-s', '--start', type=int, metavar='INDEX',
                    help="Override the starting index for this download.")
group = parser.add_argument_group(title="Managing command line arguments to youtube-dl")
group.add_argument('-G', '--global', action='store_true', dest='cfg_global',
                    help="Change the global youtube-dl arguments.")
group.add_argument('-L', '--local', action='store_true', dest='cfg_local',
                   help="Change the local (i.e. for this directory) youtube-dl arguments. "
                   "Also works for changing the URL and/or starting index.")
parser.add_argument('dl_args', nargs=argparse.REMAINDER, metavar='...',
                    help="Arguments for youtube-dl. Use this for, e.g. quality settings. "
                    "Hint: try '-- -w -c --max-quality=22/45'; the -- marks the end of arguments to %(prog)s.")
args = parser.parse_args()
while '--' in args.dl_args:
    args.dl_args.remove('--')
dl_args = ' '.join(args.dl_args)

if args.cfg_global:
    if args.dry_run:
        print "Download arguments change from '%s' to '%s'" % (gconf.get('main', 'dl-args'), dl_args)
    else:
        gconf.set('main', 'dl-args', dl_args)
        with open(GLOBAL_CONF_PATH, 'w') as fp:
            gconf.write(fp)
elif args.cfg_local:
    if args.dry_run:
        print "Download arguments change from '%s' to '%s'" % (lconf.get('main', 'dl-args'), dl_args)
        if args.url:
            print "URL changes from '%s' to '%s'" % (lconf.get('main', 'url'), args.url)
        if args.start:
            print "Start index changes from '%s' to '%d'" % (lconf.get('main', 'start'), args.start)
    else:
        lconf.set('main', 'dl-args', dl_args)
        if args.url:
            lconf.set('main', 'url', args.url)
        if args.start:
            lconf.set('main', 'start', str(args.start))
        with open(LOCAL_CONF_PATH, 'w') as fp:
            lconf.write(fp)
else:
    url = args.url
    if not url:
        url = lconf.get('main', 'url')
    if not url:
        raise ValueError('No playlist URL!')

    start = args.start
    if not start:
        start = lconf.getint('main', 'start')

    gargs = gconf.get('main', 'dl-args')
    largs = lconf.get('main', 'dl-args')

    cmd_args = ' '.join((gargs, largs, dl_args))
    cmdline = 'youtube-dl %s --playlist-start=%d' % (cmd_args, start)
    cmd_parts = cmdline.split()
    cmd_parts.extend(FORMAT_ARGS)
    cmd_parts.append(url)

    if args.dry_run:
        print cmd_parts
    else:
        retval = subprocess.call(cmd_parts)

        if retval == 0:
            lconf.set('main', 'url', url)
            lastidx = 0
            for candidate in glob.iglob('[0-9]*-*-*.*'):
                idx, unused = candidate.split('-', 1)
                if int(idx) > lastidx:
                    lastidx = int(idx)

            if lastidx > 0:
                lconf.set('main', 'start', str(lastidx + 1))

            with open(LOCAL_CONF_PATH, 'w') as fp:
                lconf.write(fp)
