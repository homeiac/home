# VLAN Troubleshooting Checklist & Guide

<!-- markdownlint-disable MD013 MD024 -->

A Virtual Local Area Network (VLAN) logically segments traffic on a network to improve performance and security. When configured correctly, VLANs let you isolate devices without additional physical switches. This guide helps network engineers diagnose common VLAN issues.

## Troubleshooting Checklist

### Multicast Forwarding Issues

#### Symptoms

- Multicast traffic does not reach all hosts
- Services relying on multicast discovery fail

#### Root Causes

- IGMP snooping misconfiguration
- Switch firmware bugs

#### Diagnostic Steps

1. Verify IGMP snooping settings on all switches.
2. Capture packets on trunk ports with `tcpdump -n -i <iface> multicast`.
3. Check router's multicast routing table with `show ip mroute` or vendor equivalent.

#### Remediation

- Enable or tune IGMP snooping on switches.
- Upgrade firmware if a known bug exists.

### Unmanaged Switches Breaking VLAN Tags

#### Symptoms

- Hosts on different VLANs suddenly communicate without routing
- Packet captures show missing 802.1Q headers

#### Root Causes

- Unmanaged switches strip VLAN tags
- Misplaced consumer-grade hardware in the path

#### Diagnostic Steps

1. Trace the cabling between affected devices.
2. Replace suspect switch with a managed one temporarily.
3. Use `tcpdump -e -n -i <iface>` to confirm whether VLAN tags are present.

#### Remediation

- Replace unmanaged switches with managed models supporting 802.1Q.
- Label cable paths to prevent incorrect hardware insertion.

### Clients Using APIPA IP Addresses

#### Symptoms

- Devices receive 169.254.x.x addresses
- DHCP requests never reach the server

#### Root Causes

- DHCP scope missing for the VLAN
- Trunk or access port misconfigured

#### Diagnostic Steps

1. Run `ipconfig` or `ifconfig` on the client to confirm the APIPA address.
2. Check switch port mode with `show vlan` or `show interface switchport`.
3. Verify DHCP server bindings and VLAN interfaces.

#### Remediation

- Create or correct the DHCP scope for the VLAN.
- Ensure the switch port is in the proper access VLAN and the trunk carries that VLAN.

### Common DHCP/VLAN Misconfigurations

#### Symptoms

- Clients timeout waiting for DHCP
- Wrong default gateway assigned

#### Root Causes

- DHCP relay (IP helper) not set on the router
- DHCP server listening on the wrong interface

#### Diagnostic Steps

1. From the router, `ping` the DHCP server over the correct VLAN interface.
2. Check relay configuration with `show running-config`.
3. Inspect DHCP server logs for requests from the VLAN.

#### Remediation

- Configure the router or layer-3 switch with the proper IP helper address.
- Bind the DHCP server to the VLAN interface.

### Trunk Port/Native VLAN Mismatch

#### Symptoms

- Intermittent connectivity between switches
- VLAN ID appears wrong on received frames

#### Root Causes

- Different native VLAN IDs on each end of a trunk
- Accidental access mode on one side

#### Diagnostic Steps

1. Run `show interfaces trunk` on both switches.
2. Use `tcpdump -e -n -i <iface>` to check incoming tag values.
3. Trace the link to ensure both ends are configured as trunk ports.

#### Remediation

- Set the native VLAN to the same value on both sides.
- Convert access ports to trunk if needed.

## Sample Troubleshooting Workflow

1. Collect symptoms from users or monitoring tools.
2. Map the physical topology and confirm switch models.
3. Capture traffic on both access and trunk ports with `tcpdump`.
4. Check switch and router configs (`show vlan`, `show running-config`).
5. Verify DHCP logs and client addressing with `ipconfig`.
6. Test connectivity using `ping` and `traceroute` between VLANs.
7. Apply fixes from the checklist and retest.

## Best Practices & Preventive Measures

- Document VLAN assignments and trunk ports.
- Keep firmware and software versions consistent across devices.
- Avoid unmanaged switches where VLANs are required.
- Use descriptive names for VLANs and maintain a change log.
- Monitor DHCP lease utilization and log errors.

## References

- [Common mistakes when setting up VLANs](https://www.xda-developers.com/mistakes-made-when-setting-up-vlans/)
