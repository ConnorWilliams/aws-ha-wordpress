# !/usr/bin/env python
# This template generates the autoscaling group which will run the wordpress
# servers. It also creates an RDS instance for the wordpress database.
# Template is modified for Sceptre (http://sceptre.ce-tools.cloudreach.com).

from troposphere import Output, Parameter, Ref, Template, Join
from troposphere import GetAZs, Select, Join, GetAtt
import troposphere.ec2 as ec2
import troposphere.elasticloadbalancing as elb
import troposphere.rds as rds

class Wordpress(object):
    def __init__(self, sceptre_user_data):
        self.template = Template()
        self.template.add_description("VPC Stack")
        self.sceptreUserData = sceptre_user_data
        self.environment = self.sceptreUserData['environment']

        self.add_parameters()

        self.defaultTags = [
            ec2.Tag('Contact', Ref(self.ownerEmailParam))
        ]
        self.namePrefix = Join("", [
            Ref(self.ownerNameParam),
            self.sceptreUserData['environment']
        ])

        print sceptre_user_data

        self.add_elb()
        self.add_security_groups()
        # self.add_rds()
        # self.add_autoscaling_group()
        #
        # self.add_outputs()

    def add_parameters(self):
        t = self.template

        self.vpcIdParam = t.add_parameter(Parameter(
            "vpcId",
            Type="String",
            Description="The VPC ID.",
        ))

        self.vpcCidrParam = t.add_parameter(Parameter(
            "vpcCidr",
            Type="String",
            Description="The VPC CIDR.",
        ))

        self.keyPairParam = t.add_parameter(Parameter(
            "keyPair",
            Type="AWS::EC2::KeyPair::KeyName",
            Description="Name of an existing EC2 KeyPair to enable SSH access to the instances.",
        ))

        self.ownerNameParam = t.add_parameter(Parameter(
            'ownerName',
            Type='String'
        ))

        self.ownerEmailParam = t.add_parameter(Parameter(
            'ownerEmail',
            Type='String'
        ))

        self.dbMultiAzParam = t.add_parameter(Parameter(
            "dbMultiAz",
            Default='false',
            Type="String",
            Description="The WordPress database admin account password",
            AllowedValues=['true', 'false'],
            ConstraintDescription="Must be either ture or false."
        ))

        self.dbNameParam = t.add_parameter(Parameter(
            "dbName",
            Type="String",
            Default="wordpressdb",
            Description="The WordPress database name",
            MinLength=1,
            MaxLength=64,
            AllowedPattern="[a-zA-Z][a-zA-Z0-9]*",
            ConstraintDescription="Must begin with a letter and contain only alphanumeric characters."
        ))

        self.dbUserParam = t.add_parameter(Parameter(
            "dbUser",
            Type="String",
            Description="The WordPress database admin account username",
            MinLength=1,
            MaxLength=16,
            AllowedPattern="[a-zA-Z][a-zA-Z0-9]*",
            ConstraintDescription="Must begin with a letter and contain only alphanumeric characters."
        ))

        self.dbPasswordParam = t.add_parameter(Parameter(
            "dbPassword",
            NoEcho=True,
            Type="String",
            Description="The WordPress database admin account password",
            MinLength=6,
            AllowedPattern="[a-zA-Z0-9]*",
            ConstraintDescription="Must only contain alphanumeric characters."
        ))

        self.dbStorageParam = t.add_parameter(Parameter(
            "dbStorage",
            NoEcho=True,
            Type="Number",
            Description="The size of the WordPress database in Gb.",
            Default='5',
            MinValue='5',
            MaxValue='1024'
        ))

    def add_elb(self):
        t = self.template

        self.elbSg = t.add_resource(ec2.SecurityGroup(
            'ElbSecurityGroup',
            VpcId=Ref(self.vpcIdParam),
            GroupDescription='Security group for ELB.',
            SecurityGroupIngress=[
                ec2.SecurityGroupRule(
                    ToPort='80',
                    FromPort='80',
                    IpProtocol='tcp',
                    CidrIp="0.0.0.0/0"
                )
                #TODO HTTPS
            ],
            Tags=self.defaultTags + [
                ec2.Tag('Name', Join("", [
                    self.namePrefix,
                    'ElbSecurityGroup'
                ]))
            ]
        ))

        self.elbListener = elb.Listener(
            'ElbListener',
            LoadBalancerPort="80",
            InstancePort="80",
            Protocol="HTTP",
            InstanceProtocol="HTTP"
        )

        self.elbHealthCheck = elb.HealthCheck(
            Target="TCP:80",
            Timeout="2",
            Interval="5",
            HealthyThreshold="2",
            UnhealthyThreshold="2"
        )

        publicSubnetIds = [ self.sceptreUserData['subnets']['publicInfraAZ1Id'],
                            self.sceptreUserData['subnets']['publicInfraAZ2Id'],
                            self.sceptreUserData['subnets']['publicInfraAZ3Id']
        ]

        self.elb = t.add_resource(elb.LoadBalancer(
            'Elb',
            Listeners=[self.elbListener],
            Scheme='internet-facing',
            HealthCheck=self.elbHealthCheck,
            CrossZone=True,
            Subnets=publicSubnetIds,
            SecurityGroups=[Ref(self.elbSg)],
            Tags=self.defaultTags + [
                ec2.Tag('Name', Join("", [
                    self.namePrefix,
                    'Elb'
                ]))
            ]
        ))
        return 0


    def add_security_groups(self):
        t = self.template

        self.asgSg = t.add_resource(ec2.SecurityGroup(
            'AsgSg',
            VpcId=Ref(self.vpcIdParam),
            GroupDescription='Security group for ASG.',
            SecurityGroupIngress=[
                ec2.SecurityGroupRule(
                    ToPort='80',
                    FromPort='80',
                    IpProtocol='tcp',
                    SourceSecurityGroupId=Ref(self.elbSg)
                )
                #TODO HTTPS
            ],
            Tags=self.defaultTags + [
                ec2.Tag('Name', Join("", [
                    self.namePrefix,
                    'AsgSg'
                ]))
            ]
        ))

        self.rdsSg = t.add_resource(ec2.SecurityGroup(
            'RdsSg',
            VpcId=Ref(self.vpcIdParam),
            GroupDescription='Security group for RDS.',
            SecurityGroupIngress=[
                ec2.SecurityGroupRule(
                    ToPort='3306',
                    FromPort='3306',
                    IpProtocol='tcp',
                    SourceSecurityGroupId=Ref(self.asgSg)
                )
            ],
            Tags=self.defaultTags + [
                ec2.Tag('Name', Join("", [
                    self.namePrefix,
                    'RdsSg'
                ]))
            ]
        ))
        return 0


    def add_rds(self):
        t = self.template

        dbSubnetIds = [ self.sceptreUserData['subnets']['privateDataAZ1Id'],
                        self.sceptreUserData['subnets']['privateDataAZ2Id'],
                        self.sceptreUserData['subnets']['privateDataAZ3Id']
        ]

        self.rdsSubnetGroup = t.add_resource(rds.DBSubnetGroup(
            'DbSubnetGroup',
            DBSubnetGroupDescription='Subnet group for RDS.',
            SubnetIds=dbSubnetIds,
            Tags=defaultTags
        ))

        self.rds = t.add_resource(rds.DBInstance(
            'RdsInstance',
            AllocatedStorage=Ref(self.dbStorageParam),
            DBInstanceClass='db.t2.micro',
            DBName=Ref(self.dbNameParam),
            DBSubnetGroupName=Ref(self.rdsSubnetGroup),
            VPCSecurityGroups=[Ref(self.rdsSg)],
            Engine='MySQL',
            EngineVersion='5.5.46',
            MasterUsername=Ref(self.dbUserParam),
            MasterUserPassword=Ref(self.dbPasswordParam),
            MultiAZ=True
        ))
        return 0

    def add_autoscaling_group(self):
        t = self.template

        return 0

    def add_outputs(self):
        t = self.template

        return 0


def sceptre_handler(sceptre_user_data):
    server = Wordpress(sceptre_user_data)
    return server.template.to_json()

if __name__ == '__main__':
    # for debugging
    import sys
    print('python version: ', sys.version, '\n')
    server = Wordpress()
    print(server.template.to_json())
