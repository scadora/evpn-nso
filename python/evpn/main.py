# -*- mode: python; python-indent: 4 -*-
import ncs
from ncs.application import Service
from resource_manager import id_allocator

class IdAllocationHelper(object):
    def __init__(self, tctx, log, root, service, xpath):
        self.username = tctx.username
        self.log = log
        self.root = root
        self.service = service
        self.xpath = xpath

    def request_id(self, pool_name, allocation_name):
        id_allocator.id_request(self.service, self.xpath, self.username,
                                pool_name, allocation_name, False)

    def read_id(self, pool_name, allocation_name):
        id = id_allocator.id_read(self.username, self.root,
                                  pool_name, allocation_name)
        if not id:
            self.log.info('%s allocation not ready' % allocation_name)
        else:
            self.log.info('Id %d allocated from %s' % (id, pool_name))

        return id

def number_to_mac(decimal_value):
    hex_value = ('%x' % decimal_value).zfill(8)
    return((':'.join(str(hex_value).zfill(12)[i:i+2] for i in range(0, 12, 2)),
            hex_value))

def get_bundle_id(root, device, proplist):
    #First check if NSO previously assigned a bundle-id for
    #any of the interfaces in the list (use the first found)
    bundle_id = next((
        value for (prop, value) in proplist for interface in device.interface
        if prop == 'bundle-id-%s-%s-%s' % (
            device.device_id, interface.interface_type, interface.interface_id)
        ), None)

    #Else, check if any interface in the list already
    #belongs to a bundle (use the first found)
    if not bundle_id:
        bundle_id = next((
            bundle_id for bundle_id in (
                root.devices.device[device.device_id].config.
                ifmgr_cfg__interface_configurations.interface_configuration[
                    'act', '%s%s' % (interface.interface_type,
                                     interface.interface_id)].
                bundle_member.id.bundle_id
                for interface in device.interface)
            if bundle_id), None)

    #Else, assign the first free bundle-id on the device
    if not bundle_id:
        bundle_id = next(
            bundle_id for bundle_id in range(1, 99)
            if not ('act', 'Bundle-Ether%d' % bundle_id) in (
                root.devices.device[device.device_id].config.
                ifmgr_cfg__interface_configurations.interface_configuration))

    #Create bundle-id entries in the opaque for all
    #interfaces in the list
    for interface in device.interface:
        prop_name = 'bundle-id-%s-%s-%s' % (
            device.device_id, interface.interface_type, interface.interface_id)
        prop = next((prop for prop in proplist if prop[0] == prop_name), None)
        if not prop:
            proplist.append((prop_name, str(bundle_id)))

    return bundle_id

def get_bvi_id(root, device, proplist):
    prop_name = 'bvi-id-%s' % (device.device_id)
    bvi_id = next((value for (prop, value) in proplist if prop == prop_name),
                  None)

    if not bvi_id:
        #Assign the first free bvi-id on the device
        bvi_id = next(
            bvi_id for bvi_id in range(1, 16000)
            if not ('act', 'BVI%d' % bvi_id) in (
                root.devices.device[device.device_id].config.
                ifmgr_cfg__interface_configurations.interface_configuration))

        proplist.append((prop_name, str(bvi_id)))

    return bvi_id


# ------------------------
# SERVICE CALLBACK EXAMPLE
# ------------------------
class EthernetSegmentServiceCallback(Service):

    # The create() callback is invoked inside NCS FASTMAP and
    # must always exist.
    @Service.create
    def cb_create(self, tctx, root, service, proplist):
        self.log.info('Service create(service=', service._path, ')')
        id_helper = IdAllocationHelper(
            tctx, self.log, root, service,
            "/evpn:ethernet-segment[segment-name='%s']" % service.segment_name)

        id_helper.request_id('esi-pool', service.segment_name)
        esi_id = id_helper.read_id('esi-pool', service.segment_name)

        if not esi_id:
            return proplist

        (system_mac, esi_id_hex) = number_to_mac(esi_id)

        for device in service.device:
            bundle_id = 0
            if (service.homing_type == 'multi-homed' or
                    len(device.interface) > 1):
                bundle_id = get_bundle_id(root, device, proplist)

            template_vars = ncs.template.Variables()
            template_vars.add('BUNDLE_ID', bundle_id)

            #Will use PW_CLASS_NAME when figure out ODN later
            template_vars.add('PW_CLASS_NAME', 'NAME_FROM_PYTHON')

            template_vars.add('SYSTEM_MAC', system_mac)
            template_vars.add('BYTES67', esi_id_hex[0:4])
            template_vars.add('BYTES89', esi_id_hex[4:8])

            template = ncs.template.Template(device)
            template.apply('ethernet-segment-template', template_vars)
            device.bundle_id = bundle_id

        return proplist


class EVPNServiceCallback(Service):

    # The create() callback is invoked inside NCS FASTMAP and
    # must always exist.
    @Service.create
    def cb_create(self, tctx, root, service, proplist):
        self.log.info('Service create(service=', service._path, ')')

        id_helper = IdAllocationHelper(
            tctx, self.log, root, service,
            "/evpn:evpn[evpn-name='%s']" % service.evpn_name)

        id_helper.request_id('evi-pool', service.evpn_name)
        evi_id = id_helper.read_id('evi-pool', service.evpn_name)

        template_vars = ncs.template.Variables()
        template_vars.add('EVI', evi_id)
        template_vars.add('PW_ID', '')
        template_vars.add('IRB_MAC', '')

        if service.evpn_type == 'vpws':
            #Create local pw-id pool for this evpn
            pw_id_pool_name = '%s-pw-id-pool' % service.evpn_name
            pw_id_pool = root.ralloc__resource_pools.idalloc__id_pool.\
                         create(pw_id_pool_name)
            pw_id_pool.range.start = 1
            pw_id_pool.range.end = 4294967295

            for vpws in service.vpws:
                id_helper.request_id(pw_id_pool_name, vpws.pw_name)
                pw_id = id_helper.read_id(pw_id_pool_name, vpws.pw_name)

                if not pw_id or not evi_id:
                    continue

                template_vars.add('PW_ID', pw_id)
                template = ncs.template.Template(vpws)
                template.apply('evpn-template', template_vars)

        elif service.evpn_type == 'bridge' and evi_id:
            template = ncs.template.Template(service.bridge)
            template.apply('evpn-template', template_vars)

        elif service.evpn_type == 'irb':
            #Get an id from ESI to generate irb_mac
            id_helper.request_id('esi-pool', service.evpn_name)
            irb_id = id_helper.read_id('esi-pool', service.evpn_name)

            if not irb_id or not evi_id:
                return proplist

            (irb_mac, _) = number_to_mac(irb_id)
            template_vars.add('IRB_MAC', irb_mac)

            # Generate bvi for all devices in all ethernet segments
            for ethernet_segment in service.irb.ethernet_segments:
                for device in root.ethernet_segment[ethernet_segment].device:
                    device_bvi = service.irb.device_bvi.create(device.device_id)
                    device_bvi.bvi_id = get_bvi_id(root, device, proplist)

            template = ncs.template.Template(service.irb)
            template.apply('evpn-template', template_vars)

        return proplist


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------
class Main(ncs.application.Application):
    def setup(self):
        # The application class sets up logging for us. It is accessible
        # through 'self.log' and is a ncs.log.Log instance.
        self.log.info('Main RUNNING')

        # Service callbacks require a registration for a 'service point',
        # as specified in the corresponding data model.
        #
        self.register_service('evpn-servicepoint', EVPNServiceCallback)
        self.register_service('ethernet-segment-servicepoint',
                              EthernetSegmentServiceCallback)

        # If we registered any callback(s) above, the Application class
        # took care of creating a daemon (related to the service/action point).

        # When this setup method is finished, all registrations are
        # considered done and the application is 'started'.

    def teardown(self):
        # When the application is finished (which would happen if NCS went
        # down, packages were reloaded or some error occurred) this teardown
        # method will be called.

        self.log.info('Main FINISHED')
