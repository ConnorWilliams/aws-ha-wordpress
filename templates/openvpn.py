# This Python template generates an OpenVPN instance.

from troposphere import Base64, Join, Parameter, Ref, Tags, GetAtt, Output, Template
from troposphere.ec2 import SecurityGroup, Tag, EIP, EIPAssociation, Instance, BlockDeviceMapping, EBSBlockDevice

class OpenVPN_Instance(object):
    def __init__(self, sceptre_user_data):
        self.template = Template()
        self.template.add_description("OpenVPN server Stack")
        self.sceptreUserData = sceptre_user_data
        self.environment = self.sceptreUserData['environment']

        self.add_parameters()

        self.defaultTags = [
            Tag('Contact', Ref(self.ownerEmailParam))
        ]
        self.namePrefix = Join("", [
            Ref(self.ownerNameParam),
            self.sceptreUserData['environment']
        ])

        self.add_vpnSecurityGroup()
        self.add_vpnInstance()
        self.add_eip()
        self.add_outputs()

    def add_parameters(self):
        t = self.template

        self.vpcIdParam = t.add_parameter(Parameter(
            "vpcId",
            Type="String"
        ))

        self.amiParam = t.add_parameter(Parameter(
            "amiId",
            Type="String"
        ))

        self.keyPairParam = t.add_parameter(Parameter(
            "keyPair",
            ConstraintDescription="must be the name of an existing EC2 KeyPair.",
            Type="AWS::EC2::KeyPair::KeyName",
            Default="openvpn",
            Description="Name of an existing EC2 KeyPair to enable SSH access to the instances",
        ))

        self.vpnSubnetParam = t.add_parameter(Parameter(
            "vpnSubnetId",
            ConstraintDescription="must be a valid EC2 subnet-id.",
            Type="String",
            MinLength="1",
            MaxLength="18",
            Description="Subnet ID instance should be launched in."
        ))

        self.instanceTypeParam = t.add_parameter(Parameter(
            "instanceType",
            Default="t2.small",
            ConstraintDescription="must be a valid EC2 instance type.",
            Type="String",
            Description="Instance type for EC2 instance."
        ))

        self.volumeSizeParam = t.add_parameter(Parameter(
            "volumeSize",
            Type="String"
        ))

        self.ownerNameParam = t.add_parameter(Parameter(
            "ownerName",
            Type="String"
        ))

        self.ownerEmailParam = t.add_parameter(Parameter(
            "ownerEmail",
            Type="String"
        ))

    def add_vpnSecurityGroup(self):
        t = self.template

        self.openVPNSecurityGroup = t.add_resource(SecurityGroup(
            "OpenVPNSecurityGroup",
            VpcId=Ref(self.vpcIdParam),
            SecurityGroupIngress=[
                {"ToPort": "443", "IpProtocol": "tcp", "CidrIp": "0.0.0.0/0", "FromPort": "443"},
                {"ToPort": "943", "IpProtocol": "tcp", "CidrIp": "0.0.0.0/0", "FromPort": "943"},
                {"ToPort": "1194", "IpProtocol": "udp", "CidrIp": "0.0.0.0/0", "FromPort": "1194"},
                {"ToPort": "22", "IpProtocol": "tcp", "CidrIp": "0.0.0.0/0", "FromPort": "22"}],
            GroupDescription="Controls access to the OpenVPN server",
            Tags=self.defaultTags + [
                Tag('Name', Join("", [
                    self.namePrefix,
                    'OpenVPNSecurityGroup'
                ]))
            ]
        ))

    def add_eip(self):
        t = self.template

        self.vpnEip = t.add_resource(EIP(
            "OpenVPNEIP",
            Domain="vpc"
        ))

        self.eip = t.add_resource(EIPAssociation(
            "ElasticIP",
            AllocationId=GetAtt(self.vpnEip, "AllocationId"),
            InstanceId=Ref(self.vpnInstance)
        ))

    def add_vpnInstance(self):
        t = self.template

        self.vpnInstance = t.add_resource(Instance(
            "OpenVPNInstance",
            ImageId=Ref(self.amiParam),
            SecurityGroupIds=[Ref(self.openVPNSecurityGroup)],
            SubnetId=Ref(self.vpnSubnetParam),
            KeyName=Ref(self.keyPairParam),
            InstanceType=Ref(self.instanceTypeParam),
            BlockDeviceMappings=[
                BlockDeviceMapping(
                    DeviceName="/dev/sda1",
                    Ebs=EBSBlockDevice(
                        VolumeSize=Ref(self.volumeSizeParam)
                    )
                )
            ],
            UserData=Base64(Join("", [
                "admin_user=",self.sceptreUserData['vpnAdminUser'],"\n",
                "admin_pw=",self.sceptreUserData['vpnAdminPw'],"\n",
                "reroute_gw=1\n",
                "reroute_dns=1\n"
                ])),
            Tags=self.defaultTags + [
                Tag('Name', Join("", [
                    self.namePrefix,
                    'OpenVPNInstance'
                ]))
            ]
        ))

    def add_outputs(self):
        t = self.template

        self.privateAddressOutput = t.add_output(Output(
            "OpenVPNPrivateIP",
            Description="Private IP address of OpenVPN Instance",
            Value=GetAtt(self.vpnInstance.name, "PrivateIp")
            ))

        self.eipAddressOutput = t.add_output(Output(
            "OpenVPNElasticIP",
            Description="IP address used to connect to VPN",
            Value=GetAtt(self.vpnInstance.name, "PublicIp")
            ))

        self.instanceIdOutput = t.add_output(Output(
            "OpenVPNInstanceID",
            Description="Instance ID of OpenVPN server",
            Value=Ref(self.vpnInstance)
            ))

        self.openVPNSecurityGroupIDOutput = t.add_output(Output(
            "vpnSecurityGroupID",
            Description="ID of OpenVPN Security Group",
            Value=Ref(self.openVPNSecurityGroup)
            ))

def sceptre_handler(sceptre_user_data):
    openvpn = OpenVPN_Instance(sceptre_user_data)
    return openvpn.template.to_json()

if __name__ == "__main__":
    # for debugging
    import sys
    print('python version: ', sys.version, '\n')
    openvpn = OpenVPN_Instance()
    print(openvpn.template.to_json())
