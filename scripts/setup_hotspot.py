"""
Sets up (or switches off) the kiosk's own Wi-Fi hotspot from .env.

hostapd broadcasts an open network, dnsmasq hands out addresses and answers
every name with the Pi, and an nftables table limits the hotspot interface to
DHCP, DNS, the Portal's port and the captive-portal probe responder (port 80 is
redirected to it), with no forwarding anywhere. See
docs/adr/0007-own-hotspot-replaces-raspap-captive-portal.md, GitHub issue #29
and docs/adr/0008-captive-portal-detection-without-a-splash-page.md.

Usage (on the kiosk Pi, from anywhere in the repo):
    sudo python3 scripts/setup_hotspot.py              # apply
    sudo python3 scripts/setup_hotspot.py --dry-run    # print what it would do
    python3 scripts/setup_hotspot.py --root /tmp/stage # write files under /tmp/stage, run nothing

WIFI_HOTSPOT_ENABLED in .env decides the direction: true enables hostapd and
dnsmasq; false disables them and removes the files this script wrote. The
firewall stays on either way. Re-running is safe; files this script didn't
write are moved to /var/backups/ssp-hotspot/<timestamp>/ before being replaced.

Stdlib only: it runs under the Pi's system python3 via sudo, not the app venv.
"""
import argparse
import datetime
import ipaddress
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

MARKER = "Managed by SSP-Plus scripts/setup_hotspot.py"

HOSTAPD_CONF = "etc/hostapd/hostapd.conf"
DNSMASQ_CONF = "etc/dnsmasq.d/ssp-hotspot.conf"
NM_UNMANAGED_CONF = "etc/NetworkManager/conf.d/ssp-hotspot-unmanaged.conf"
FIREWALL_NFT = "etc/ssp-hotspot/firewall.nft"
IP_UNIT = "etc/systemd/system/ssp-hotspot-ip.service"
FIREWALL_UNIT = "etc/systemd/system/ssp-hotspot-firewall.service"
HOSTAPD_DROPIN = "etc/systemd/system/hostapd.service.d/ssp-hotspot.conf"
DNSMASQ_DROPIN = "etc/systemd/system/dnsmasq.service.d/ssp-hotspot.conf"
BACKUP_DIR = "var/backups/ssp-hotspot"

# Files that exist only while the hotspot is on. The firewall files are left
# out on purpose: they stay in place when the hotspot is switched off.
HOTSPOT_FILES = [HOSTAPD_CONF, DNSMASQ_CONF, NM_UNMANAGED_CONF, IP_UNIT, HOSTAPD_DROPIN, DNSMASQ_DROPIN]

PACKAGES = ["hostapd", "dnsmasq", "nftables"]

# RaspAP + Nodogsplash/openNDS, from the plan ADR 0007 replaced.
RASPAP_SERVICES = ["raspapd", "restapi", "nodogsplash", "opennds", "lighttpd"]
# Templated per interface, e.g. raspap-network-activity@wlan0.service.
RASPAP_ACTIVITY_UNIT = "raspap-network-activity@{interface}.service"
RASPAP_PACKAGES = ["nodogsplash", "opennds"]
RASPAP_UNIT_FILES = [
    "etc/systemd/system/raspapd.service",
    "etc/systemd/system/raspap-network-activity@.service",
]
RASPAP_MARKERS = ["etc/raspap", "etc/nodogsplash", "etc/opennds", *RASPAP_UNIT_FILES]
# RaspAP's dnsmasq drop-ins (090_raspap.conf, 090_wlan0.conf) would fight ours.
RASPAP_DNSMASQ_GLOB = "090_*.conf"

# Ports the Portal and the probe responder must never share: SSH, DNS, DHCP.
RESERVED_PORTS = {22, 53, 67}

_IFNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,15}$")
_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$")
_KIOSK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class HotspotSettings:
    enabled: bool
    interface: str
    ssid: str
    country: str
    channel: int
    address: ipaddress.IPv4Interface
    portal_hostname: str
    portal_port: int
    captive_port: int
    admin_dashboard_port: int
    kiosk_id: str

    @classmethod
    def from_config(cls, config) -> "HotspotSettings":
        """Build from a config.Config (or anything with the same properties),
        collecting every problem instead of stopping at the first."""
        problems = []

        try:
            address = ipaddress.IPv4Interface(config.wifi_hotspot_address)
        except ValueError:
            address = None
            problems.append(f"WIFI_HOTSPOT_ADDRESS={config.wifi_hotspot_address!r} is not an IPv4 address/prefix")

        settings = cls(
            enabled=config.wifi_hotspot_enabled,
            interface=config.wifi_hotspot_interface,
            ssid=config.wifi_hotspot_ssid,
            country=config.wifi_hotspot_country,
            channel=config.wifi_hotspot_channel,
            address=address,
            portal_hostname=config.portal_hostname,
            portal_port=config.wifi_portal_port,
            captive_port=config.wifi_captive_port,
            admin_dashboard_port=config.admin_dashboard_port,
            kiosk_id=config.kiosk_id,
        )
        problems += settings._problems()
        if problems:
            raise SettingsError("\n".join(f"  - {p}" for p in problems))
        return settings

    def _problems(self) -> List[str]:
        problems = []
        if not _IFNAME_RE.match(self.interface):
            problems.append(f"WIFI_HOTSPOT_INTERFACE={self.interface!r} is not a valid interface name")
        ssid_bytes = self.ssid.encode("utf-8")
        if not 1 <= len(ssid_bytes) <= 32 or any(c in self.ssid for c in "\r\n\0"):
            problems.append("WIFI_HOTSPOT_SSID must be 1-32 bytes with no line breaks")
        if not re.fullmatch(r"[A-Z]{2}", self.country):
            problems.append(f"WIFI_HOTSPOT_COUNTRY={self.country!r} must be a two-letter country code")
        if not 1 <= self.channel <= 13:
            problems.append(f"WIFI_HOTSPOT_CHANNEL={self.channel} must be a 2.4 GHz channel (1-13)")
        if self.address is not None:
            net = self.address.network
            if not net.is_private:
                problems.append(f"WIFI_HOTSPOT_ADDRESS={self.address} must be in a private range")
            elif not 16 <= net.prefixlen <= 29:
                problems.append(f"WIFI_HOTSPOT_ADDRESS={self.address} prefix must be /16 to /29")
            elif self.address.ip != net.network_address + 1:
                problems.append(
                    f"WIFI_HOTSPOT_ADDRESS={self.address} must be the first host of its subnet "
                    f"({net.network_address + 1}/{net.prefixlen})"
                )
        if not _HOSTNAME_RE.match(self.portal_hostname):
            problems.append(f"PORTAL_HOSTNAME={self.portal_hostname!r} is not a valid DNS name")
        if not 1 <= self.portal_port <= 65535:
            problems.append(f"WIFI_PORTAL_PORT={self.portal_port} is out of range")
        elif self.portal_port in RESERVED_PORTS:
            problems.append(f"WIFI_PORTAL_PORT={self.portal_port} clashes with SSH/DNS/DHCP")
        elif self.portal_port == self.admin_dashboard_port:
            problems.append(f"WIFI_PORTAL_PORT={self.portal_port} is the Admin Dashboard's port, which must stay closed")
        if not 1 <= self.captive_port <= 65535:
            problems.append(f"WIFI_CAPTIVE_PORT={self.captive_port} is out of range")
        elif self.captive_port in RESERVED_PORTS:
            problems.append(f"WIFI_CAPTIVE_PORT={self.captive_port} clashes with SSH/DNS/DHCP")
        elif self.captive_port in (self.portal_port, self.admin_dashboard_port):
            problems.append(
                f"WIFI_CAPTIVE_PORT={self.captive_port} must differ from the Portal's and the dashboard's ports"
            )
        if self.kiosk_id and not _KIOSK_ID_RE.match(self.kiosk_id):
            problems.append(f"KIOSK_ID={self.kiosk_id!r} must be lowercase letters, digits and hyphens")
        return problems

    @property
    def dhcp_range(self):
        """Every host after the Pi's own address."""
        net = self.address.network
        return net.network_address + 2, net.broadcast_address - 1


# ---------------------------------------------------------------------------
# Rendered files
# ---------------------------------------------------------------------------

def _header(comment="#") -> str:
    return f"{comment} {MARKER} -- edit .env and re-run it instead of editing this file.\n"


def render_hostapd(s: HotspotSettings) -> str:
    # Open network on purpose: no wpa= lines (ADR 0007). ap_isolate stops
    # phones on the hotspot from reaching each other.
    return _header() + f"""interface={s.interface}
driver=nl80211
ssid2={_hostapd_ssid(s.ssid)}
utf8_ssid=1
country_code={s.country}
ieee80211d=1
hw_mode=g
channel={s.channel}
ieee80211n=1
wmm_enabled=1
auth_algs=1
ignore_broadcast_ssid=0
ap_isolate=1
"""


def _hostapd_ssid(ssid: str) -> str:
    # ssid2 with a P"..." string takes any printable text, quotes included.
    escaped = ssid.replace("\\", "\\\\").replace('"', '\\"')
    return f'P"{escaped}"'


def render_dnsmasq(s: HotspotSettings) -> str:
    start, end = s.dhcp_range
    ip = s.address.ip
    # no-resolv with no server= lines: dnsmasq never looks anything up on the
    # internet. Instead every name is answered with the Pi (address=/#/), so
    # the OSes' connectivity checks reach the probe responder (ADR 0008) and
    # any name typed on the hotspot, the Portal's included, lands on the Pi.
    # Windows also checks that dns.msftncsi.com has its real, fixed address.
    # except-interface=lo keeps the Pi's own lookups away from it.
    # The router option points at the Pi so phones treat the Wi-Fi as a
    # normal network; the firewall drops anything they try to forward.
    return _header() + f"""interface={s.interface}
except-interface=lo
bind-dynamic
no-resolv
no-hosts
domain-needed
bogus-priv
address=/#/{ip}
address=/dns.msftncsi.com/131.107.255.255
dhcp-range={start},{end},{s.address.netmask},1h
dhcp-option=option:router,{ip}
dhcp-option=option:dns-server,{ip}
dhcp-authoritative
"""


def render_firewall(s: HotspotSettings) -> str:
    # Our own table, so loading it never touches anyone else's rules (Tailscale
    # keeps its own). "table ...; delete table ..." makes reloads idempotent.
    # Every other base chain on these hooks still runs; a drop here is final.
    # Phones' internet traffic is rejected, not dropped, so it fails at once:
    # a silent drop made each page wait ~10 s on anything it tried to fetch
    # from the internet. Input stays a silent drop, except HTTPS: the OSes'
    # HTTPS connectivity checks are reset so they fail at once.
    # The hotspot's port 80 is redirected to the probe responder (ADR 0008);
    # input sees the redirected port.
    return f"""#!/usr/sbin/nft -f
{_header()}
table inet ssp_hotspot
delete table inet ssp_hotspot

table inet ssp_hotspot {{
\tchain input {{
\t\ttype filter hook input priority filter - 10; policy accept;
\t\tiifname != "{s.interface}" accept
\t\tudp dport 67 accept comment "DHCP"
\t\tudp dport 53 accept comment "DNS"
\t\ttcp dport 53 accept comment "DNS"
\t\ttcp dport {s.portal_port} accept comment "Portal"
\t\ttcp dport {s.captive_port} accept comment "captive-portal probe responder"
\t\ttcp dport 443 reject with tcp reset comment "HTTPS connectivity checks fail at once"
\t\tcounter drop comment "everything else on the hotspot, SSH and the dashboard included"
\t}}

\tchain prerouting {{
\t\ttype nat hook prerouting priority dstnat; policy accept;
\t\tiifname "{s.interface}" ip daddr {s.address.ip} tcp dport 80 redirect to :{s.captive_port} comment "captive-portal checks"
\t}}

\tchain forward {{
\t\ttype filter hook forward priority filter - 10; policy accept;
\t\tiifname "{s.interface}" meta l4proto tcp counter reject with tcp reset comment "no forwarding from the hotspot"
\t\tiifname "{s.interface}" counter reject with icmpx admin-prohibited comment "no forwarding from the hotspot"
\t\toifname "{s.interface}" counter drop comment "no forwarding into the hotspot"
\t}}
}}
"""


def render_nm_unmanaged(s: HotspotSettings) -> str:
    # Bookworm's NetworkManager would otherwise try to use the interface as a
    # client and fight hostapd for it.
    return _header() + f"""[keyfile]
unmanaged-devices=interface-name:{s.interface}
"""


def render_ip_unit(s: HotspotSettings) -> str:
    dev = f"sys-subsystem-net-devices-{s.interface}.device"
    return _header() + f"""[Unit]
Description=SSP-Plus hotspot address on {s.interface}
BindsTo={dev}
After={dev}
Before=hostapd.service dnsmasq.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=-/usr/sbin/rfkill unblock wlan
ExecStart=/usr/sbin/ip link set {s.interface} up
ExecStart=/usr/sbin/ip addr replace {s.address} dev {s.interface}
ExecStop=/usr/sbin/ip addr flush dev {s.interface}

[Install]
WantedBy=multi-user.target
"""


def render_firewall_unit() -> str:
    return _header() + f"""[Unit]
Description=SSP-Plus hotspot firewall (nftables table inet ssp_hotspot)
DefaultDependencies=no
Wants=network-pre.target
Before=network-pre.target hostapd.service dnsmasq.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f /{FIREWALL_NFT}
ExecStop=/usr/sbin/nft delete table inet ssp_hotspot

[Install]
WantedBy=multi-user.target
"""


def render_service_dropin() -> str:
    # hostapd and dnsmasq only start once the address and firewall are in place.
    return _header() + """[Unit]
Requires=ssp-hotspot-ip.service ssp-hotspot-firewall.service
After=ssp-hotspot-ip.service ssp-hotspot-firewall.service
"""


# ---------------------------------------------------------------------------
# Plan: a list of actions, built without touching the system
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Write:
    path: str
    content: str
    mode: int = 0o644


@dataclass(frozen=True)
class Remove:
    """Delete a file this script wrote (one without the marker is left alone)."""
    path: str


@dataclass(frozen=True)
class Backup:
    """Move a file or directory someone else wrote into the backup directory."""
    path: str


@dataclass(frozen=True)
class Run:
    argv: tuple
    check: bool = True


def detect_raspap(root: Path) -> List[str]:
    """RaspAP/Nodogsplash leftovers found under root, as root-relative paths."""
    found = [m for m in RASPAP_MARKERS if (root / m).exists()]
    dnsmasq_d = root / "etc/dnsmasq.d"
    if dnsmasq_d.is_dir():
        found += sorted(p.relative_to(root).as_posix() for p in dnsmasq_d.glob(RASPAP_DNSMASQ_GLOB))
    return found


def is_managed(path: Path) -> bool:
    try:
        return MARKER in path.read_text(encoding="utf-8", errors="replace")[:500]
    except OSError:
        return False


def plan(
    s: HotspotSettings,
    root: Path,
    installed: Callable[[Iterable[str]], List[str]] = lambda names: [],
) -> list:
    """
    Everything the script will do, in order. `installed(names)` returns which
    of the named Debian packages are installed (only consulted for the RaspAP
    clean-up; the default says none, which is right for a staging root).
    """
    actions: list = []

    raspap = detect_raspap(root)
    if raspap:
        units = [f"{unit}.service" for unit in RASPAP_SERVICES]
        units.append(RASPAP_ACTIVITY_UNIT.format(interface=s.interface))
        for unit in units:
            actions.append(Run(("systemctl", "disable", "--now", unit), check=False))
        purge = installed(RASPAP_PACKAGES)
        if purge:
            actions.append(Run(("apt-get", "purge", "-y", *purge)))
        for path in raspap:
            if path.startswith("etc/dnsmasq.d/") or path in RASPAP_UNIT_FILES:
                actions.append(Backup(path))

    files = {
        FIREWALL_NFT: render_firewall(s),
        FIREWALL_UNIT: render_firewall_unit(),
    }
    if s.enabled:
        actions.append(Run(("apt-get", "install", "-y", "--no-install-recommends", *PACKAGES)))
        files.update({
            HOSTAPD_CONF: render_hostapd(s),
            DNSMASQ_CONF: render_dnsmasq(s),
            NM_UNMANAGED_CONF: render_nm_unmanaged(s),
            IP_UNIT: render_ip_unit(s),
            HOSTAPD_DROPIN: render_service_dropin(),
            DNSMASQ_DROPIN: render_service_dropin(),
        })
    else:
        actions.append(Run(("apt-get", "install", "-y", "--no-install-recommends", "nftables")))

    for path, content in files.items():
        existing = root / path
        if existing.exists() and not is_managed(existing):
            actions.append(Backup(path))
        actions.append(Write(path, content))

    if not s.enabled:
        for unit in ("hostapd", "dnsmasq", "ssp-hotspot-ip"):
            actions.append(Run(("systemctl", "disable", "--now", f"{unit}.service"), check=False))
        for path in HOTSPOT_FILES:
            if (root / path).exists():
                actions.append(Remove(path))

    actions.append(Run(("systemctl", "daemon-reload")))
    actions.append(Run(("systemctl", "enable", "ssp-hotspot-firewall.service")))
    actions.append(Run(("systemctl", "restart", "ssp-hotspot-firewall.service")))
    actions.append(Run(("systemctl", "reload-or-restart", "NetworkManager.service"), check=False))

    if s.enabled:
        # Debian ships hostapd masked until it has a config.
        actions.append(Run(("systemctl", "unmask", "hostapd.service")))
        for unit in ("ssp-hotspot-ip", "hostapd", "dnsmasq"):
            actions.append(Run(("systemctl", "enable", f"{unit}.service")))
        for unit in ("ssp-hotspot-ip", "hostapd", "dnsmasq"):
            actions.append(Run(("systemctl", "restart", f"{unit}.service")))

    return actions


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def describe(action) -> str:
    if isinstance(action, Write):
        return f"write   /{action.path} ({oct(action.mode)})"
    if isinstance(action, Remove):
        return f"remove  /{action.path}"
    if isinstance(action, Backup):
        return f"backup  /{action.path}"
    return "run     " + " ".join(action.argv) + ("" if action.check else "  (failure ignored)")


def apply(actions: list, root: Path, dry_run: bool = False, run_commands: bool = True,
          now: Optional[datetime.datetime] = None) -> None:
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    backup_dir = root / BACKUP_DIR / stamp

    for action in actions:
        line = describe(action)
        if dry_run or (isinstance(action, Run) and not run_commands):
            print(f"[skip] {line}")
            continue
        print(f">>> {line}")

        if isinstance(action, Write):
            target = root / action.path
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".ssp-tmp")
            tmp.write_text(action.content, encoding="utf-8")
            os.chmod(tmp, action.mode)
            os.replace(tmp, target)
        elif isinstance(action, Remove):
            target = root / action.path
            if is_managed(target):
                target.unlink()
            else:
                print("    left in place: not written by this script")
        elif isinstance(action, Backup):
            source = root / action.path
            if source.exists():
                dest = backup_dir / action.path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(dest))
                print(f"    moved to /{dest.relative_to(root)}")
        elif isinstance(action, Run):
            result = subprocess.run(action.argv)
            if action.check and result.returncode != 0:
                raise SystemExit(f"command failed ({result.returncode}): {' '.join(action.argv)}")


def installed_packages(names: Iterable[str]) -> List[str]:
    found = []
    for name in names:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", name], capture_output=True, text=True
        )
        if result.returncode == 0 and "install ok installed" in result.stdout:
            found.append(name)
    return found


def load_settings() -> HotspotSettings:
    # config.py reads .env from the working directory, same as the app.
    os.chdir(REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT / "SSP"))
    from config import get_config
    return HotspotSettings.from_config(get_config())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    parser.add_argument("--root", default="/", help="write files under this directory instead of / and run no commands")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    live = root == Path("/")

    try:
        settings = load_settings()
    except SettingsError as e:
        print(f"❌ .env has hotspot settings that can't be used:\n{e}", file=sys.stderr)
        return 2

    if live and not args.dry_run and os.geteuid() != 0:
        print("❌ Run with sudo (or use --dry-run / --root).", file=sys.stderr)
        return 1

    state = "ON" if settings.enabled else "OFF"
    print(f"Hotspot {state}: SSID {settings.ssid!r} on {settings.interface}, {settings.address}")
    actions = plan(settings, root, installed_packages if live else (lambda names: []))
    apply(actions, root, dry_run=args.dry_run, run_commands=live)

    if settings.enabled:
        print(f"\nPortal on the hotspot: https://{settings.portal_hostname}:{settings.portal_port}/upload")
        print(f"Captive-portal checks: hotspot port 80 -> {settings.captive_port}")
        if not settings.kiosk_id:
            print("⚠️  KIOSK_ID is blank in .env; set it before printing this kiosk's sticker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
