import os
from shutil import copy2
import sys
import thread
from time import sleep


class Reloader(object):
    """Reloads a given Python module if changes are detected in any specified file"""
    def __init__(self, watched_files, update_folder=None, before_reload=None, interval=5):
        self.watched_files_mtimes = [(f, os.path.getmtime(f)) for f in watched_files]
        self.before_reload = before_reload
        self.interval = interval

        if update_folder:
            update_required = False
            print "Checking for updates in folder '{}'".format(update_folder)
            for f, mtime in self.watched_files_mtimes:
                try:
                    server_mtime = os.path.getmtime(os.path.join(update_folder, f))
                except Exception as e:
                    print "\tUnable to check for an updated file '{}': {}".format(f, e)
                    continue

                if round(mtime) == round(server_mtime):
                    print "\t'{}' - up to date".format(f)
                else:
                    print "\t'{}' - update required ({} != {})".format(f, mtime, server_mtime)
                    copy2(os.path.join(update_folder, f), os.getcwd())
                    update_required = True

            if update_required:
                print 'Reloading...'
                sleep(1)
                self.reload()

            print

        thread.start_new_thread(self._check_loop, ())

    def reload(self):
        if self.before_reload:
            self.before_reload()
        os.execv(sys.executable, ['python'] + sys.argv)  # Restart the script

    def _check_loop(self):
        while True:
            sleep(self.interval)
            for f, mtime in self.watched_files_mtimes:
                try:
                    if os.path.getmtime(f) != mtime:
                        print 'Modification detected in {}; reloading\n'.format(f)
                        self.reload()
                except WindowsError:
                    print 'Unable to check file {} modification time'.format(f)
