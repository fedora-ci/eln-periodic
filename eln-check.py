#!/usr/bin/python3

import argparse
import datetime
import koji
import logging
import os
import re
import requests
import rpm

from jinja2 import Template


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
    # if build['epoch']:
    #     epoch = str(build['epoch'])
    # else:
    #     epoch = "0"
    # #  epoch's are important, but we just want to
    # #  know if we need to rebuild the package
    # #  so for this, they are not important.
    epoch = "0"
    version = build['version']
    p = re.compile(".(fc|eln)[0-9]*")
    release = re.sub(p, "", build['release'])
    return epoch, version, release


def is_higher(evr1, evr2):
    return rpm.labelCompare(evr1, evr2) > 0


def get_build(package, tag):
    builds = session.listTagged(tag, package=package, latest=True)
    if builds:
        return builds[0]
    else:
        return None


def get_distro_packages():
    """
    Fetches the list of desired sources from Content Resolver
    for each of the given 'arches'.
    """
    merged_packages = set()

    distro_url = "https://tiny.distro.builders"
    distro_view = "eln"
    arches = ["aarch64", "armv7hl", "ppc64le", "s390x", "x86_64"]
    which_source = ["source", "buildroot-source"]

    for arch in arches:
        for this_source in which_source:
            url = (
                "{distro_url}"
                "/view-{this_source}-package-name-list--view-{distro_view}--{arch}.txt"
            ).format(distro_url=distro_url, this_source=this_source, distro_view=distro_view, arch=arch)

            logging.debug("downloading {url}".format(url=url))

            r = requests.get(url, allow_redirects=True)
            for line in r.text.splitlines():
                merged_packages.add(line)

    logging.debug("Found a total of {} packages".format(len(merged_packages)))

    return merged_packages


def is_excluded(package):
    """
    Return True if package is permanently excluded from rebuild automation.
    """
    excludes = [
        "kernel",  # it takes too much infra resources to try kernel builds automatically
        "kernel-headers",  # it takes too much infra resources to try kernel builds automatically
        "kernel-tools",  # it takes too much infra resources to try kernel builds automatically
        "ipa",  # freeipa is rename ipa in ELN
        "shim",  # shim has its own building proceedure
    ]
    exclude_prefix = [
        "shim-",
    ]

    if package in excludes:
        return True
    for prefix in exclude_prefix:
        if package.startswith(prefix):
            return True
    return False


def is_on_hold(package):
    """
    Return True if package is temporarily on hold from rebuild automation.
    """
    hold = [
        "freeipa", # freeipa always shows up that it needs to be built
    ]
    hold_prefix = [
    ]

    if package in hold:
        return True
    for prefix in hold_prefix:
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
        return package, rawhide_build, None

    logging.debug("Checking {0}".format(eln_build))

    if is_higher(evr(rawhide_build), evr(eln_build)):
        return package, rawhide_build, eln_build

    return None


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument("-v", "--verbose",
                        help="Enable debug logging",
                        action='store_true')

    parser.add_argument("-o", "--output",
                        help="Filepath for the output",
                        default="rebuild.txt")

    parser.add_argument("-w", "--webpage",
                        help="Filepath for the webpage",
                        default="status.html")

    parser.add_argument("-s", "--status",
                        help="Filepath for the status",
                        default="status.txt")

    parser.add_argument("-u", "--untag",
                        help="Filepath for the untag list",
                        default="untag.txt")

    parser.add_argument("-r", "--successrate",
                        help="Filepath for the success rate percentage webpage",
                        default="successrate.txt")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    counter = 0
    packages_done = []

    overall_packagelist = get_distro_packages()
    eln_builds = get_eln_builds()

    # Create the buildable list
    with open("buildable-eln-packages.txt", 'w') as b:
        for package_name in overall_packagelist:
            if package_name not is_on_hold(package_name) and not is_excluded(package_name):
                b.write("{0}\n".format(package_name))

    f = open(args.output, 'w')
    s = open(args.status, 'w')
    u = open(args.untag, 'w')

    for eln_build in eln_builds:
        if not eln_build['name'] in overall_packagelist:
            logging.warning("Adding %s to the untag list" % (eln_build['name']))
            u.write("{0}\n".format(eln_build['name']))

        if is_excluded(eln_build['name']):
            logging.warning("Skipping %s because it is excluded" % (eln_build['name']))
            packages_done.append(eln_build['name'])
            continue

        rawhide_build = get_build(eln_build['name'], rawhide)

        if not rawhide_build:
            logging.warning("No Rawhide build found for {0}".format(eln_build['name']))
            packages_done.append(eln_build['name'])
            continue

        diff = diff_with_rawhide(package=eln_build['name'], eln_build=eln_build, rawhide_build=rawhide_build)
        if diff:
            if is_on_hold(eln_build['name']):
                logging.info("Held Package Difference found: {0} {1}".format(diff[1]['nvr'], diff[2]['nvr']))
            else:
                counter += 1
                logging.info("Difference found: {0} {1}".format(diff[1]['nvr'], diff[2]['nvr']))
                f.write("{0}\n".format(diff[1]['build_id']))
            if diff[2]:
                build_status = "OLD"
            else:
                build_status = "NONE"
        else:
            build_status = "SAME"
        s.write("%s %s %s %s\n" % (eln_build['name'], build_status, rawhide_build['nvr'], eln_build['nvr']))
        packages_done.append(eln_build['name'])

    # Work on the packagelist from Content Resolver
    for package_name in overall_packagelist:
        if package_name not in packages_done:
            if is_excluded(package_name):
                print("    Skipping %s because it is excluded" % (package_name))
                packages_done.append(package_name)
                continue

            rawhide_build = get_build(package_name, rawhide)

            if not rawhide_build:
                logging.warning("No Rawhide build found for {0}".format(package_name))
                packages_done.append(package_name)
                continue

            eln_build = get_build(package_name, "eln")

            if not eln_build:
                build_status = "NONE"
                eln_nvr = "NONE"
                if is_on_hold(package_name):
                    logging.info("Held Package not found: {0}".format(package_name))
                else:
                    counter += 1
                    logging.info("No ELN build for: {0}".format(package_name))
                    f.write("{0}\n".format(rawhide_build['build_id']))

            else:
                diff = diff_with_rawhide(package_name, eln_build=eln_build, rawhide_build=rawhide_build)
                if diff:
                    if diff[2]:
                        build_status = "OLD"
                        eln_nvr = eln_build['nvr']
                    else:
                        build_status = "NONE"
                        eln_nvr = "NONE"
                else:
                    build_status = "SAME"
                    eln_nvr = eln_build['nvr']
            s.write("%s %s %s %s\n" % (package_name, build_status, rawhide_build['nvr'], eln_nvr))
            packages_done.append(package_name)

    u.close()
    f.close()
    s.close()

    logging.info("Total differences {0}".format(counter))
    os.system("sort -u -o %s %s" % (args.status, args.status))

    # Create Webpage
    color_same = "#00FF00"
    color_old = "#FFFFCC"
    color_none = "#FF0000"
    with open('status.html.jira') as f:
        tmpl = Template(f.read())
    status_packagelist = open(args.status).read().splitlines()
    package_list = []
    counter_same = 0
    counter_old = 0
    counter_none = 0
    for package_line in status_packagelist:
        ps = package_line.split()
        this_package = {}
        this_package['name'] = ps[0]
        this_package['status'] = ps[1]
        this_package['raw_nvr'] = ps[2]
        this_package['eln_nvr'] = ps[3]
        if ps[1] == "SAME":
            this_package['color'] = color_same
            counter_same += 1
        elif ps[1] == "OLD":
            this_package['color'] = color_old
            counter_old += 1
        else:
            this_package['color'] = color_none
            counter_none += 1
        package_list.append(this_package)
    counter_total = counter_same + counter_old + counter_none
    if counter_total == 0:
        percentage_same = "?%"
        percentage_old = "?%"
        percentage_none = "?%"
    else:
        percentage_same = "{:.2%}".format(counter_same / counter_total)
        percentage_old = "{:.2%}".format(counter_old / counter_total)
        percentage_none = "{:.2%}".format(counter_none / counter_total)
    with open(args.webpage, 'w') as w:
        w.write(tmpl.render(
            this_date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
            count_same=counter_same,
            percent_same=percentage_same,
            count_old=counter_old,
            percent_old=percentage_old,
            count_none=counter_none,
            percent_none=percentage_none,
            count_total=counter_total,
            packages=package_list))

    with open(args.successrate, 'w') as r:
        r.write("{0}\n".format(percentage_same))
