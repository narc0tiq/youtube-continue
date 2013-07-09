#!/usr/bin/python
from ConfigParser import ConfigParser
import argparse, os, shlex, subprocess, sys, glob

# Exit codes
OK = 0
# Unrecoverable errors
MISSING_URL = 1
# Safety issues
CHANGED_URL = 101
# Passthrough offset
YTDL_OFFSET = 10000

GLOBAL_CONF_PATH = os.path.expanduser('~/.config/youtube-continue.ini')
LOCAL_CONF_PATH = './youtube-continue.ini'
FORMAT_ARGS = ['-o', '%(playlist_index)s-%(title)s.%(id)s.%(ext)s']

# Load the global and local configuration files.
gconf = ConfigParser({'dl-args': ''})
gconf.read([GLOBAL_CONF_PATH])
if not gconf.has_section('main'):
    gconf.add_section('main')
lconf = ConfigParser({'dl-args': '', 'url': '', 'start': '1'})
lconf.read([LOCAL_CONF_PATH])
if not lconf.has_section('main'):
    lconf.add_section('main')

# Command-line options
parser = argparse.ArgumentParser(description="Manage youtube-dl playlist directories.",
                                 epilog="""If --configure is present, the URL and start index will be ignored and
                                           youtube-dl will not be called. Otherwise, the arguments passed to youtube-dl
                                           will be a merger of the global, local, and command-line arguments, in that
                                           order.

                                           Note that youtube-continue sets a custom filename template for youtube-dl.
                                           Changing the template may break some functionality.""")
parser.add_argument('-d', '--dry-run', action='store_true', dest='dry_run',
                    help="Do not run youtube-dl, instead print the command line that would be passed to it. "
                    "With --configure, prints the old and new configuration values, but does not update them.")
parser.add_argument('-u', '--url',
                    help="A URL that youtube-dl will understand as a playlist reference, "
                    "e.g. http://youtube.com/playlist?list=xxxx. Only necessary for the first run.")
parser.add_argument('-s', '--start', type=int, metavar='INDEX',
                    help="Manually set the starting index for this download.")

group = parser.add_argument_group(title="Managing stored settings.")
group.add_argument('--configure', action='append', choices=["local", "global", "both"],
                   type=str.lower, default=[],
                   help="Change youtube-continue configuration.")
group.add_argument('-G', '--global', action='append_const', const="global", dest='configure',
                   help="Change global configuration.  Shorthand for --configure=global.")
group.add_argument('-L', '--local', action='append_const', const="local", dest='configure',
                   help="Change local (i.e. for this directory) configuration."
                   "Shorthand for --configure=local.")
parser.add_argument('dl_args', nargs=argparse.REMAINDER, metavar='...',
                    help="Arguments for youtube-dl. Use this for, e.g. quality settings. "
                    "Hint: try '-- -w -c --max-quality=22/45'; the -- marks the end of arguments to %(prog)s.")

def get_last_index():
    """
    Searches the current directory for the highest-numbered video downloaded.
    """
    last_index = 0
    for candidate in glob.iglob('[0-9]*-*-*.*'):
        idx, unused = candidate.split('-', 1)
        if int(idx) > last_index:
            last_index = int(idx)

    return last_index

def merge_args(*argument_sets):
    """
    Merges the specified argument sets, giving priority to the last one.

    If an argument set is empty, it's ignored.  If it starts with +, the remainder is appended to
    the existing argument set.  Otherwise, it replaces the existing argument set.
    """
    args = ""
    for argument_set in filter(None, map(str.strip, argument_sets)):
        if argument_set[0] == "+":
            # Continue the previous argument set.
            args += " " + argument_set.lstrip("+ ")
        else:
            # Replace the previous argument set
            args = argument_set

    # We might have picked up an extra space at the start; remove it.
    return args.lstrip()

def main():
    # Parse the command line.
    args = parser.parse_args()

    # Strip the argument-separator from the list of arguments to pass on.
    while '--' in args.dl_args:
        args.dl_args.remove('--')
    dl_args = ' '.join(args.dl_args)

    # Read the --configure options.
    configure_global = False
    configure_local = False
    for entry in args.configure:
        if entry == "local":
            configure_local = True
        elif entry == "global":
            configure_global = True
        elif entry == "both":
            configure_local = True
            configure_global = True
            break # Nothing else to do.

    # -G : Change global options
    if configure_global:
        if args.dry_run:
            print "[--dry-run]: Global download arguments would change from '%s' to '%s'" % (gconf.get('main', 'dl-args'), dl_args)
        else:
            gconf.set('main', 'dl-args', dl_args)
            with open(GLOBAL_CONF_PATH, 'w') as fp:
                gconf.write(fp)

    # -L : Change local options
    if configure_local:
        if args.dry_run:
            print "[--dry-run]: Download arguments would change from '%s' to '%s'" % (lconf.get('main', 'dl-args'), dl_args)
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

    # If we edited either the global or local config, we'll skip the download step.
    if configure_global or configure_local:
        return OK

    # Get the playlist URL.
    url = args.url
    config_url = lconf.get('main', 'url')
    if url and config_url:
        # We got a URL on the command line, but already had one stored.
        if url == config_url:
            print "You don't need to specify the playlist URL again; it's already stored."
        else:
            print "Playlist URL mismatch!  If you want to update the URL, run:"
            print "%s --configure=local --url='%s'" % (sys.argv[0], url)
            return CHANGED_URL
    elif url:
        # We got a URL on the command line, and need to store it for later use.
        if args.dry_run:
            print "[--dry-run]: Would store playlist URL:", url
        else:
            lconf.set('main', 'url', args.url)
            print "Storing playlist URL..."
            with open(LOCAL_CONF_PATH, 'w') as fp:
                lconf.write(fp)
            print "URL stored.  You won't need to specify it again."
    elif config_url:
        # No URL set on the command line, but that's fine, because we already have it stored.
        print "Continuing stored playlist."
        url = config_url
    else:
        print 'No playlist URL!'
        return MISSING_URL

    # Get the playlist index to start at.
    start = args.start
    commandline_start = True
    if not start:
        # This will default to 1 if not set.
        start = lconf.getint('main', 'start')
        commandline_start = False

    if start == 0:
        # Programmers.  Always wanting to start at zero.
        start = 1
    elif start < 0:
        print "Starting index seems to have gone negative somehow."
        if commandline_start:
            print "Did you make a typo?"
        else:
            print "You can reset it with:"
            print sys.argv[0] + " --config=local --start 1"

    # Combine the global, local, and commandline dl_args, using the "clobber if not explicitly appended"
    # algorithm.
    cmd_args = merge_args(gconf.get('main', 'dl-args'), lconf.get('main', 'dl-args'), dl_args)

    # Build the final command line.
    cmdline = 'youtube-dl %s --playlist-start=%d' % (cmd_args, start)
    cmd_parts = shlex.split(cmdline)
    cmd_parts.extend(FORMAT_ARGS)
    cmd_parts.append(url)

    if args.dry_run:
        # Dry run: Print it out and exit.
        print "[--dry-run]: Would execute:", cmd_parts
        return OK

    retval = subprocess.call(cmd_parts)

    # Figure out where we should start next time.
    last_index = get_last_index()
    if last_index > 0:
        if start > last_index:
            # We didn't manage to download anything, but we should remember where the user
            # wanted to start.
            next_index = start
        elif retval == 0:
            # If we exited successfully, we can assume the last video downloaded correctly.
            next_index = last_index + 1
        else:
            # If not, we'll make sure it's complete next time, before continuing onwards.
            next_index = last_index

        # Save the next_index for next time.
        lconf.set('main', 'start', str(next_index))
        with open(LOCAL_CONF_PATH, 'w') as fp:
            lconf.write(fp)

    if retval == 0:
        return OK
    else:
        return YTDL_OFFSET + retval

if __name__ == "__main__":
    ret = main()

    if isinstance(ret, int):
        sys.exit(ret)
