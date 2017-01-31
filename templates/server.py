# !/usr/bin/env python
# This template generates the autoscaling group which will run the wordpress
# servers. It also creates an RDS instance for the wordpress database.
# Template is modified for Sceptre (http://sceptre.ce-tools.cloudreach.com).

from troposphere import Output, Parameter, Ref, Template, Join
from troposphere import GetAZs, Select, Join, GetAtt
import troposphere.ec2 as ec2

class Wordpress(object):
    def __init__(self, sceptre_user_data):
        self.template = Template()
        self.template.add_description("VPC Stack")
        self.sceptreUserData = sceptre_user_data
        self.environment = self.sceptreUserData['environment']
        self.numAz = self.sceptreUserData['numAz']

        self.add_parameters()

        self.defaultTags = [
            ec2.Tag('Contact', Ref(self.ownerEmailParam))
        ]
        self.namePrefix = Join("", [
            Ref(self.ownerNameParam),
            self.sceptreUserData['environment']
        ])

        self.add_elb()
        self.add_autoscaling_group()
        self.add_rds()

        self.add_outputs()

    def add_parameters(self):
        t = self.template

        self.keyPairParam = t.add_parameter(Parameter(
            "KeyPair",
            Type="AWS::EC2::KeyPair::KeyName",
            Description="Name of an existing EC2 KeyPair to enable SSH access to the instances.",
        ))

        self.dbMultiAzParam = t.add_parameter(Parameter(
            "DbMultiAz",
            Default='false',
            Type="String",
            Description="The WordPress database admin account password",
            AllowedValues=['true', 'false'],
            ConstraintDescription="Must be either ture or false."
        ))

        self.dbNameParam = t.add_parameter(Parameter(
            "DbName",
            Type="String",
            Default="wordpressdb",
            Description="The WordPress database name",
            MinLength=1,
            MaxLength=64,
            AllowedPattern="[a-zA-Z][a-zA-Z0-9]*",
            ConstraintDescription="Must begin with a letter and contain only alphanumeric characters."
        ))

        self.dbUserParam = t.add_parameter(Parameter(
            "DbUser",
            Type="String",
            Description="The WordPress database admin account username",
            MinLength=1,
            MaxLength=16,
            AllowedPattern="[a-zA-Z][a-zA-Z0-9]*",
            ConstraintDescription="Must begin with a letter and contain only alphanumeric characters."
        ))

        self.dbPasswordParam = t.add_parameter(Parameter(
            "DbPassword",
            NoEcho=True,
            Type="String",
            Description="The WordPress database admin account password",
            MinLength=6,
            AllowedPattern="[a-zA-Z0-9]*",
            ConstraintDescription="Must only contain alphanumeric characters."
        ))

        self.dbStorageParam = t.add_parameter(Parameter(
            "DbStorage",
            NoEcho=True,
            Type="Number",
            Description="The size of the WordPress database in Gb.",
            Default=5,
            MinValue=5,
            MaxValue=1024
        ))

    def add_elb(self):
        # ELB
        return 0

    def add_autoscaling_group(self):
        t = self.template

        self.serverSg = t.add_resource(ec2.SecurityGroup(
            "WordpressServerSecurityGroup",
            VpcId=Ref(self.vpc_id_param),
            SecurityGroupIngress=[
                {"ToPort": "443", "IpProtocol": "tcp", "CidrIp": "0.0.0.0/0", "FromPort": "443"},
                {"ToPort": "943", "IpProtocol": "tcp", "CidrIp": "0.0.0.0/0", "FromPort": "943"},
                {"ToPort": "1194", "IpProtocol": "udp", "CidrIp": "0.0.0.0/0", "FromPort": "1194"},
                {"ToPort": "22", "IpProtocol": "tcp", "CidrIp": "0.0.0.0/0", "FromPort": "22"}],
            GroupDescription="Controls access to the OpenVPN server",
            Tags=self.DEFAULT_TAGS + [
               ec2.Tag("Name", "OpenVPNSecurityGroup")
            ]
        ))

        self.serverLaunchConfig = t.add_resource(LaunchConfiguration(
            "LaunchConfiguration",
            Metadata=autoscaling.Metadata(
                cloudformation.Init({
                    "config": cloudformation.InitConfig(
                        files=cloudformation.InitFiles({
                            "/etc/rsyslog.d/20-somethin.conf": cloudformation.InitFile(
                                source=Join('', [
                                    "http://",
                                    Ref(DeployBucket),
                                    ".s3.amazonaws.com/stacks/",
                                    Ref(RootStackName),
                                    "/env/etc/rsyslog.d/20-somethin.conf"
                                ]),
                                mode="000644",
                                owner="root",
                                group="root",
                                authentication="DeployUserAuth"
                            )
                        }),
                        services={
                            "sysvinit": cloudformation.InitServices({
                                "rsyslog": cloudformation.InitService(
                                    enabled=True,
                                    ensureRunning=True,
                                    files=['/etc/rsyslog.d/20-somethin.conf']
                                )
                            })
                        }
                    )
                }),
                cloudformation.Authentication({
                    "DeployUserAuth": cloudformation.AuthenticationBlock(
                        type="S3",
                        accessKeyId=Ref(DeployUserAccessKey),
                        secretKey=Ref(DeployUserSecretKey)
                    )
                })
            ),
            UserData=Base64(Join('', [
                "#!/bin/bash\n",
                "cfn-signal -e 0",
                "    --resource AutoscalingGroup",
                "    --stack ", Ref("AWS::StackName"),
                "    --region ", Ref("AWS::Region"), "\n"
            ])),
            ImageId=Ref(AmiId),
            KeyName=Ref(KeyName),
            BlockDeviceMappings=[
                ec2.BlockDeviceMapping(
                    DeviceName="/dev/sda1",
                    Ebs=ec2.EBSBlockDevice(
                        VolumeSize="8"
                    )
                ),
            ],
            SecurityGroups=[self.serverSg],
            InstanceType="t2.micro", #TODO Parameterize
        ))

        # AS Group
        return 0

    def add_rds(self):
        # RDS Instance
        # RDS Security Group
        return 0

    def add_outputs(self):
        t = self.template

        return 0


def sceptre_handler(sceptre_user_data):
    server = Vpc(sceptre_user_data)
    return vpc.template.to_json()

if __name__ == '__main__':
    # for debugging
    import sys
    print('python version: ', sys.version, '\n')
    vpc = Vpc()
    print(vpc.template.to_json())
