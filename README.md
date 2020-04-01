# Deploying EVPN Services

This demo shows how NSO can simplify the deployment of 3 EVPN use cases: VPWS, bridge and IRB.  The EVPN model is designed to take the minimum possible input to create a valid EVPN service.

This demo only supports IOS XR devices using NETCONF.

## Getting Started

### Pre-requisites

The focus of this demo is on EVPN only.  All other aspects of the network are expected to be preconfigured, including:

- v4/v6 addressing
- IGP
- BGP (including neighbors, EVPN address family, etc)
- VRFs and L3VPN (for IRB)

Sample initial configurations are available in the examples directory.

### Resource-manager

This demo makes use of the resource-manager bundle package to manage the allocation of ESIs, EVIs, and MAC addresses.  Ensure that your NSO instance has the resource-manager package installed.  The resource-manager package is available on https://software.cisco.com 

## Usage

### Resource-pools
The EVPN demo allocates resources from an `esi-pool` and an `evi-pool`.  To use the default values, perform a load-merge on the `resource-pools.xml` in the main directory before configuring anything else. 

### Ethernet-Segments

The first step is to configure the ethernet-segments that will be used in the EVPN services.  Ethernet-segments consist of a list of devices and interfaces.  All ethernet-segments default to multi-homed, all-active unless otherwise specified.

Example:

```
ethernet-segment SJC1
device pe1 interface HundredGigE 0/0/0/0
device pe2 interface HundredGigE 0/0/0/0

ethernet-segment DEN1 homing-type single-homed
device pe3 interface HundredGigE 0/0/0/0
```

More examples are available in the examples directory.

### EVPN Service

The following EVPN types are supported: VPWS, bridge and IRB.

A VPWS consists of a list of exactly two ethernet-segments.  If the same ethernet-segment is used in more than one EVPN service, a VLAN encapsulation must be specified.

Example:

```
evpn ACME_PWs
 vpws PW1 ethernet-segments [ SJC1 DEN1 ] encapsulation dot1q 10
 vpws PW2 ethernet-segments [ SJC1 DEN1 ] encapsulation dot1q 20
 vpws PW3 ethernet-segments [ SJC1 DEN1 ] encapsulation dot1q 30
```

### Testing
The function pack was tested on a small ASR9000-based topology.  Base configurations are available in the examples directory.
