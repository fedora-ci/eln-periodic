#!/usr/bin/python3

import argparse
import logging
import os
import re
import rpm
import datetime
from jinja2 import Template

import koji

# Connect to Fedora Koji instance
session = koji.ClientSession('https://koji.fedoraproject.org/kojihub')

# Get versioned tag for rawhide ('f34')
rawhide = session.getFullInheritance('rawhide')[0]['name']


def get_eln_builds():
    return session.listTagged("eln", latest=True) 

def no_dist_nvr(build):
    nvr = build['nvr']
    return nvr.rsplit(".", 1)[0]

def evr(build):
    #if build['epoch']:
    #    epoch = str(build['epoch'])
    #else:
    #    epoch = "0"
		## epoch's are important, but we just want to
		##   know if we need to rebuild the package
		##   so for this, they are not important.
    epoch = "0"
    version = build['version']
    p = re.compile(".(fc|eln)[0-9]*")              
    release = re.sub(p, "", build['release'])
    return (epoch, version, release)

def is_higher(evr1, evr2):
    return (rpm.labelCompare(evr1, evr2) > 0)
    
def get_build(package, tag):
    builds = session.listTagged(tag, package=package, latest=True)
    if builds:
        return builds[0]
    else:
        return None

def is_excluded(package):
    """
    Return True if package is excluded from rebuild automation.
    """

    excludes = [
        "kernel", # it takes too much infra resources to try kernel builds automatically
        "ghc",    # ghc on arm depends on LLVM7.0 which is not in eln, leaving it put until issues is resolved
    ]
    exclude_prefix = [
        "ghc-",
    ]

    if package in excludes:
        return True
    for prefix in exclude_prefix:
        if package.startswith(prefix):
            return True
    return False
    
def diff_with_rawhide(package, eln_build=None, rawhide_build=None):
    """Compares version of ELN and Rawhide packages. If eln_build is not known,
    fetches the latest ELN build from Koji.

    If there is a difference, return tuple (package, rawhide_build, eln_build),
    else return None.
    """

    if not eln_build:
        eln_build = get_build(package, "eln")

    if not eln_build:
        logging.debug("No build found for {0} in ELN".format(package))
        return (package, rawhide_build, None)
            
    logging.debug("Checking {0}".format(eln_build))

    if is_higher(evr(rawhide_build), evr(eln_build)):
        return (package, rawhide_build, eln_build)
    
    return None
 

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    
    parser.add_argument("-v", "--verbose",
                        help="Enable debug logging",
                        action='store_true',
    )
    parser.add_argument("-o", "--output",
                        help="Filepath for the output",
                        default="rebuild.txt"
    )
    parser.add_argument("-w", "--webpage",
                        help="Filepath for the webpage",
                        default="status.html"
    )
    parser.add_argument("-s", "--status",
                        help="Filepath for the status",
                        default="status.txt"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    eln_builds = get_eln_builds()

    counter = 0

    f = open(args.output,'w')
    s = open(args.status,'w')

    for eln_build in eln_builds:
        rawhide_build = get_build(eln_build['name'], rawhide)

        if not rawhide_build:
            logging.warning("No Rawhide build found for {0}".format(eln_build['name']))
            continue
    
        diff = diff_with_rawhide(package=eln_build['name'], eln_build=eln_build, rawhide_build=rawhide_build)
        if diff:
            counter += 1
            logging.info("Difference found: {0} {1}".format(diff[1]['nvr'], diff[2]['nvr']))
            if is_excluded(diff[0]):
                logging.warning("Skipping as excluded")
                continue
            
            f.write("{0}\n".format(diff[1]['build_id']))
            if diff[2]:
              build_status = "OLD"
            else:
              build_status = "NONE"
        else:
            build_status = "SAME"
        s.write("%s %s %s %s\n" % (eln_build['name'], build_status, rawhide_build['nvr'], eln_build['nvr']))

    f.close()
    s.close()
    os.system("sort -u -o %s %s" % (args.status, args.status))

    logging.info("Total differences {0}".format(counter))

    # Create Webpage
    color_same="#00FF00"
    color_old="#FFFFCC"
    color_none="#FF0000"
    with open('status.html.jira') as f:
      tmpl = Template(f.read())
    status_packagelist = open(args.status).read().splitlines()
    package_list = []
    for package_line in status_packagelist:
      ps = package_line.split()
      this_package = {}
      this_package['name'] = ps[0]
      this_package['status'] = ps[1]
      this_package['raw_nvr'] = ps[2]
      this_package['eln_nvr'] = ps[3]
      if ps[1] == "SAME":
        this_package['color'] = color_same 
      elif ps[1] == "OLD":
        this_package['color'] = color_old 
      else:
        this_package['color'] = color_none
      package_list.append(this_package)
    w = open(args.webpage,'w')
    w.write(tmpl.render(
      this_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
      packages = package_list
      ))
    w.close()
