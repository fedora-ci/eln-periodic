#!/usr/bin/python3

import koji

import argparse
import datetime
import jinja2
import logging
import os
import re
import requests
import rpm


class BuildSource:

    def __init__(self, source_id=None, infra=None, tag=None, make_cache=True):
        """Setup a source of the builds

        :infra: Koji or Brew session,
        :tag: Koji or Brew tag
        """

        if source_id:
            infra, tag = self._configure_source(source_id)

        self.infra = infra
        self.tag = tag
        self.cache = {}

        if make_cache:
            self.make_cache()

    def __str__(self):
        return f'{self.tag}'

    def _configure_source(self, source_id):
        if source_id == "rawhide":
            infra = koji.ClientSession('https://koji.fedoraproject.org/kojihub')
            tag = infra.getFullInheritance('rawhide')[0]['name']
        if source_id == "eln":
            infra = koji.ClientSession('https://koji.fedoraproject.org/kojihub')
            tag = "eln"
        if source_id == "rhel":
            # FIXME
            infra = koji.ClientSession('https://brew')
            tag = "rhel-9.0.0-alpha"

        return infra, tag

    def get_build(self, package):
        """Find the latest build of a package available in the build source

        Return None if there is no builds found
        """

        if package in self.cache:
            logging.debug(f'Read cached for {package} in {self}')
            return self.cache[package]

        builds = self.infra.listTagged(self.tag, package=package, latest=True)

        if builds:
            return builds[0]
        else:
            return None

    def make_cache(self):
        """Fetch all builds from tag"""

        logging.debug(f'Make cache for {self}...')
        builds = self.infra.listTagged(self.tag, latest=True)
        for build in builds:
            self.cache[build["name"]] = build
        logging.debug(f'Done Make cache for {self}')


class Comparison:

    status = {
        -2: "ERROR",
        -1: "NEW",
        0: "SAME",
        1: "OLD",
        2: "NONE",
    }

    def __init__(self, content, source1, source2):
        self.content = content
        self.source1 = source1
        self.source2 = source2

        self.results = {}

    def compare_one(self, package):
        """Returm comparison data for a package

        Return dictionary with items: status, nvr1, nvr2.
        """
        if package not in content:
            logging.warning("Package {package} is not in the content set")

        if package in self.results:
            return self.results[package]

        build1 = self.source1.get_build(package)
        build2 = self.source2.get_build(package)

        if not build1:
            logging.warning(f'Package {package} not found in {source1}')
            return {
                "status": self.status[-2],
                "nvr1": None,
                "nvr2": None,
            }

        if not build2:
            logging.info(f'Package {package} not found in {source2}')
            return {
                "status": self.status[2],
                "nvr1": build1["nvr"],
                "nvr2": None,
            }

        return {
                "status": self.status[compare_builds(build1, build2)],
                "nvr1": build1["nvr"],
                "nvr2": build2["nvr"],
        }

    def compare_all(self):
        for package in content:
            logging.debug(f'Processing package {package}')
            self.results[package] = self.compare_one(package)
        return self.results

    def count(self):
        stats = {}
        for item in self.results.values():
            value = item["status"]
            if value not in stats:
                stats[value] = 0
            stats[value] += 1
        stats["total"] = sum(stats.values())
        return stats

    def render(self, tmpl_path="templates", output_path="output", fmt="all"):
        os.makedirs(output_path, exist_ok=True)

        j2_env = jinja2.Environment(loader=jinja2.FileSystemLoader(tmpl_path))
        templates = j2_env.list_templates(extensions="j2")
        if fmt != "all":
            fmtlist = fmt.split(",")
            templates = [
                name for name in templates if name.split(".")[-2] in fmtlist
            ]

        for tmpl_name in templates:
            tmpl = j2_env.get_template(tmpl_name)
            tmpl.stream(
                source1=self.source1,
                source2=self.source2,
                results=self.results,
                stats=self.count(),
                date=datetime.datetime.now()
            ).dump(
                os.path.join(
                    output_path,
                    tmpl_name[:-3],
                )
            )


def get_content(distro_view="eln"):
    """Builds the full list of packages for the distro from the Content Resolver

    Merges result for all architectures.
    """
    merged_packages = set()

    distro_url = "https://tiny.distro.builders"
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


def evr(build):
    """Get epoch, version, release data from the build

    We currently reset Epoch value to 0, because we have number of cases where
    epoch of a package in Rawhide is different from that of ELN.

    We remove dist tag data from the release, so that we can compare nvr's
    between different distributions.
    """

    epoch = "0"

    version = build['version']
    p = re.compile(".(fc|eln)[0-9]*")
    release = re.sub(p, "", build['release'])

    return (epoch, version, release)


def compare_builds(build1, build2):
    """Compare versions of two builds

    Return -1, 0 or 1 if version of build1 is lesser, equal or greater than build2.
    """

    evr1 = evr(build1)
    evr2 = evr(build2)

    return rpm.labelCompare(evr1, evr2)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-v", "--verbose",
        help="Enable debug logging",
        action='store_true',
    )

    parser.add_argument(
        "-c", "--cache",
        action="store_true",
        help="Enable cache of build sources",
    )

    parser.add_argument(
        "-f", "--format",
        default="all",
        help="Comma-separated list of output formats. Supported: json, html, txt, all.",
    )

    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Path where to store rendered results",
    )

    parser.add_argument(
        "source1",
        choices=["rawhide", "eln", "rhel"],
        help="First source of package builds",
    )

    parser.add_argument(
        "source2",
        choices=["rawhide", "eln", "rhel"],
        help="Second source of package builds",
    )

    parser.add_argument(
        "packages",
        nargs='*',
        default=None,
        help="Optional list of packages to compare",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    source1 = BuildSource(source_id=args.source1, make_cache=args.cache)
    source2 = BuildSource(source_id=args.source2, make_cache=args.cache)

    if args.packages:
        content = args.packages
    else:
        content = sorted(get_content())

    C = Comparison(content, source1, source2)

    C.compare_all()
    logging.info(C.count())
    C.render(output_path=args.output, fmt=args.format)
