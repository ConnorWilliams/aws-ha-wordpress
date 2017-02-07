# !/usr/bin/env python
# This template generates the autoscaling group which will run the wordpress
# servers. It also creates an RDS instance for the wordpress database.
# Template is modified for Sceptre (http://sceptre.ce-tools.cloudreach.com).

from troposphere import Output, Parameter, Ref, Template, Join, Base64
from troposphere import GetAZs, Select, Join, GetAtt
from troposphere.ec2 import Tag, SecurityGroup, SecurityGroupRule
from troposphere.elasticloadbalancing import LoadBalancer, Listener, HealthCheck
from troposphere.rds import DBSubnetGroup, DBInstance
from troposphere.autoscaling import AutoScalingGroup, LaunchConfiguration
from troposphere.policies import UpdatePolicy, AutoScalingRollingUpdate
from troposphere.autoscaling import Tag as ASTag
from troposphere import cloudformation as cfn

class Wordpress(object):
    def __init__(self, sceptre_user_data):
        self.template = Template()
        self.template.add_description("VPC Stack")
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

        self.add_elb()
        self.add_security_groups()
        self.add_rds()
        self.add_autoscaling_group()

        self.add_outputs()

    def add_parameters(self):
        t = self.template

        self.vpcIdParam = t.add_parameter(Parameter(
            "vpcId",
            Type="String",
            Description="The VPC ID.",
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

        self.vpnSgIdParam = t.add_parameter(Parameter(
            "vpnSgId",
            Type="String",
            Description="The ID of the VPN security group."
        ))

    def add_elb(self):
        t = self.template

        self.elbSg = t.add_resource(SecurityGroup(
            'ElbSecurityGroup',
            VpcId=Ref(self.vpcIdParam),
            GroupDescription='Security group for ELB.',
            SecurityGroupIngress=[
                SecurityGroupRule(
                    ToPort='80',
                    FromPort='80',
                    IpProtocol='tcp',
                    CidrIp="0.0.0.0/0"
                )
                #TODO HTTPS
            ],
            Tags=self.defaultTags + [
                Tag('Name', Join("", [
                    self.namePrefix,
                    'ElbSecurityGroup'
                ]))
            ]
        ))

        self.elbListener = Listener(
            'ElbListener',
            LoadBalancerPort="80",
            InstancePort="80",
            Protocol="HTTP",
            InstanceProtocol="HTTP"
        )

        self.elbHealthCheck = HealthCheck(
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

        self.elb = t.add_resource(LoadBalancer(
            'Elb',
            Listeners=[self.elbListener],
            Scheme='internet-facing',
            HealthCheck=self.elbHealthCheck,
            CrossZone=True,
            Subnets=publicSubnetIds,
            SecurityGroups=[Ref(self.elbSg)],
            Tags=self.defaultTags + [
                Tag('Name', Join("", [
                    self.namePrefix,
                    'Elb'
                ]))
            ]
        ))
        return 0


    def add_security_groups(self):
        t = self.template

        self.asgSg = t.add_resource(SecurityGroup(
            'AsgSg',
            VpcId=Ref(self.vpcIdParam),
            GroupDescription='Security group for ASG.',
            SecurityGroupIngress=[
                SecurityGroupRule(
                    ToPort='80',
                    FromPort='80',
                    IpProtocol='tcp',
                    SourceSecurityGroupId=Ref(self.elbSg)
                ),
                SecurityGroupRule(
                    ToPort='22',
                    FromPort='22',
                    IpProtocol='tcp',
                    SourceSecurityGroupId=Ref(self.vpnSgIdParam)
                )
                #TODO HTTPS
            ],
            Tags=self.defaultTags + [
                Tag('Name', Join("", [
                    self.namePrefix,
                    'AsgSg'
                ]))
            ]
        ))

        self.rdsSg = t.add_resource(SecurityGroup(
            'RdsSg',
            VpcId=Ref(self.vpcIdParam),
            GroupDescription='Security group for RDS.',
            SecurityGroupIngress=[
                SecurityGroupRule(
                    ToPort='3306',
                    FromPort='3306',
                    IpProtocol='tcp',
                    SourceSecurityGroupId=Ref(self.asgSg)
                )
            ],
            Tags=self.defaultTags + [
                Tag('Name', Join("", [
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

        self.rdsSubnetGroup = t.add_resource(DBSubnetGroup(
            'DbSubnetGroup',
            DBSubnetGroupDescription='Subnet group for RDS.',
            SubnetIds=dbSubnetIds,
            Tags=self.defaultTags + [
                Tag('Name', Join("", [
                    self.namePrefix,
                    'DbSubnetGroup'
                ]))
            ]
        ))

        self.rds = t.add_resource(DBInstance(
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
            MultiAZ=Ref(self.dbMultiAzParam)
        ))
        return 0

    def add_autoscaling_group(self):
        t = self.template

        self.asgLaunchConfig = t.add_resource(LaunchConfiguration(
            'ASGLaunchConfig',
            ImageId='ami-0b33d91d', #TODO Mapping for different regions
            InstanceMonitoring=False,
            AssociatePublicIpAddress=False,
            InstanceType="t2.micro",
            SecurityGroups=[Ref(self.asgSg)],
            KeyName=Ref(self.keyPairParam),
            UserData=Base64(Join("",
                [
                    "#!/bin/bash -xe\n",
                    "yum update -y aws-cfn-bootstrap\n",

                    "/opt/aws/bin/cfn-init -v ",
                    "         --stack ", { "Ref" : "AWS::StackName" },
                    "         --resource LaunchConfig ",
                    "         --configsets wordpress_install ",
                    "         --region ", { "Ref" : "AWS::Region" }, "\n",

                    # "/opt/aws/bin/cfn-signal -e $? ",
                    # "         --stack ", { "Ref" : "AWS::StackName" },
                    # "         --resource WebServerGroup ",
                    # "         --region ", { "Ref" : "AWS::Region" }, "\n"
                ]
            )),
            Metadata=cfn.Metadata(
                cfn.Init(
                    cfn.InitConfigSets(
                        wordpress_install=['install_cfn', 'install_chefdk', "install_chef", "install_wordpress", "run_chef"]
                    ),
                    install_cfn=cfn.InitConfig(
                        # Starts cfn-hup daemon which detects changes in metadata
                        # and runs user-specified actions when a change is detected.
                        # This allows configuration updates through UpdateStack.
                        # The cfn-hup.conf file stores the name of the stack and
                        # the AWS credentials that the cfn-hup daemon targets.
                        # The cfn-hup daemon parses and loads each file in the /etc/cfn/hooks.d directory.
                        files={
                            "/etc/cfn/cfn-hup.conf": {
                                "content": { "Fn::Join": [ "", [
                                    "[main]\n",
                                    "stack=", { "Ref": "AWS::StackId" }, "\n",
                                    "region=", { "Ref": "AWS::Region" }, "\n"
                                ]]},
                                "mode"  : "000400",
                                "owner" : "root",
                                "group" : "root"
                            },
                            "/etc/cfn/hooks.d/cfn-auto-reloader.conf": {
                                "content": { "Fn::Join": [ "", [
                                    "[cfn-auto-reloader-hook]\n",
                                    "triggers=post.update\n",
                                    "path=Resources.LaunchConfig.Metadata.AWS::CloudFormation::Init\n",
                                    "action=/opt/aws/bin/cfn-init -v ",
                                    "         --stack ", { "Ref" : "AWS::StackName" },
                                    "         --resource LaunchConfig ",
                                    "         --configsets wordpress_install ",
                                    "         --region ", { "Ref" : "AWS::Region" }, "\n"
                                ]]},
                                "mode"  : "000400",
                                "owner" : "root",
                                "group" : "root"
                            }
                        },
                        services={
                            "sysvinit" : {
                                "cfn-hup" : { "enabled" : "true", "ensureRunning" : "true",
                                "files" : ["/etc/cfn/cfn-hup.conf", "/etc/cfn/hooks.d/cfn-auto-reloader.conf"] }
                            }
                        }
                    ),
                    install_chefdk=cfn.InitConfig(
                        packages={
                            "rpm" : {
                                "chefdk" : "https://opscode-omnibus-packages.s3.amazonaws.com/el/6/x86_64/chefdk-0.2.0-2.el6.x86_64.rpm"
                            }
                        }
                    ),
                    install_chef=cfn.InitConfig(
                        sources={
                            #  Set up a local Chef repository on the instance.
                            "/var/chef/chef-repo" : "http://github.com/opscode/chef-repo/tarball/master"
                        },
                        files={
                            #  Chef installation file.
                            "/tmp/install.sh" : {
                                "source" : "https://www.opscode.com/chef/install.sh",
                                "mode"  : "000400",
                                "owner" : "root",
                                "group" : "root"
                            },
                            # Knife configuration file.
                            "/var/chef/chef-repo/.chef/knife.rb" : {
                                "content" : { "Fn::Join": [ "", [
                                    "cookbook_path [ '/var/chef/chef-repo/cookbooks' ]\n",
                                    "node_path [ '/var/chef/chef-repo/nodes' ]\n"
                                ]]},
                                "mode"  : "000400",
                                "owner" : "root",
                                "group" : "root"
                            },
                            # Chef client configuration file.
                            "/var/chef/chef-repo/.chef/client.rb" : {
                                "content" : { "Fn::Join": [ "", [
                                    "cookbook_path [ '/var/chef/chef-repo/cookbooks' ]\n",
                                    "node_path [ '/var/chef/chef-repo/nodes' ]\n"
                                ]]},
                                "mode"  : "000400",
                                "owner" : "root",
                                "group" : "root"
                            }
                        },
                        commands={
                            #  make the /var/chef directory readable, run the
                            # Chef installation, and then start Chef local mode
                            # by using the client.rb file that was created.
                            # The commands are run in alphanumeric order.
                            "01_make_chef_readable" : {
                                "command" : "chmod +rx /var/chef"
                            },
                            "02_install_chef" : {
                                "command" : "bash /tmp/install.sh",
                                "cwd"  : "/var/chef"
                            },
                            "03_create_node_list" : {
                                "command" : "chef-client -z -c /var/chef/chef-repo/.chef/client.rb",
                                "cwd" : "/var/chef/chef-repo",
                                "env" : { "HOME" : "/var/chef" }
                            }
                        }
                    ),
                    install_wordpress=cfn.InitConfig(
                        # Installs WordPress by using a WordPress cookbook.
                        files={
                            # knife.rb and client.rb files are overwritten to
                            # point to the cookbooks that are required to install WordPress.
                            "/var/chef/chef-repo/.chef/knife.rb" : {
                                "content" : { "Fn::Join": [ "", [
                                    "cookbook_path [ '/var/chef/chef-repo/cookbooks/wordpress/berks-cookbooks' ]\n",
                                    "node_path [ '/var/chef/chef-repo/nodes' ]\n"
                                ]]},
                                "mode"  : "000400",
                                "owner" : "root",
                                "group" : "root"
                            },
                            "/var/chef/chef-repo/.chef/client.rb" : {
                                "content" : { "Fn::Join": [ "", [
                                    "cookbook_path [ '/var/chef/chef-repo/cookbooks/wordpress/berks-cookbooks' ]\n",
                                    "node_path [ '/var/chef/chef-repo/nodes' ]\n"
                                ]]},
                                "mode"  : "000400",
                                "owner" : "root",
                                "group" : "root"
                            },
                            #  Specify the Amazon RDS database instance as the WordPress database
                            "/var/chef/chef-repo/cookbooks/wordpress/attributes/aws_rds_config.rb" : {
                                "content": { "Fn::Join": [ "", [
                                    "normal['wordpress']['db']['pass'] = '", Ref(self.dbPasswordParam), "'\n",
                                    "normal['wordpress']['db']['user'] = '", Ref(self.dbUserParam), "'\n",
                                    "normal['wordpress']['db']['host'] = '", GetAtt(self.rds, "Endpoint.Address"), "'\n",
                                    "normal['wordpress']['db']['name'] = '", Ref(self.dbNameParam), "'\n"
                                ]]},
                                "mode"  : "000400",
                                "owner" : "root",
                                "group" : "root"
                            }
                        },
                        commands={
                            "01_get_cookbook" : {
                                "command" : "knife cookbook site download wordpress",
                                "cwd" : "/var/chef/chef-repo",
                                "env" : { "HOME" : "/var/chef" }
                            },
                            "02_unpack_cookbook" : {
                                "command" : "tar xvfz /var/chef/chef-repo/wordpress*",
                                "cwd" : "/var/chef/chef-repo/cookbooks"
                            },
                            "03_init_berkshelf": {
                                "command" : "berks init /var/chef/chef-repo/cookbooks/wordpress --skip-vagrant --skip-git",
                                "cwd" : "/var/chef/chef-repo/cookbooks/wordpress",
                                "env" : { "HOME" : "/var/chef" }
                            },
                            "04_vendorize_berkshelf" : {
                                "command" : "berks vendor",
                                "cwd" : "/var/chef/chef-repo/cookbooks/wordpress",
                                "env" : { "HOME" : "/var/chef" }
                            },
                            "05_configure_node_run_list" : {
                                "command" : "knife node run_list add -z `knife node list -z` recipe[wordpress]",
                                "cwd" : "/var/chef/chef-repo",
                                "env" : { "HOME" : "/var/chef" }
                            }
                        }

                    ),
                    run_chef=cfn.InitConfig(
                        commands={
                            "01_run_chef_client" : {
                                "command" : "chef-client -z -c /var/chef/chef-repo/.chef/client.rb",
                                "cwd" : "/var/chef/chef-repo",
                                "env" : { "HOME" : "/var/chef" }
                            }
                        }
                    )
                )
            )
        ))

        webserverSubnetIds = [ self.sceptreUserData['subnets']['privateWebAZ1Id'],
                            self.sceptreUserData['subnets']['privateWebAZ2Id'],
                            self.sceptreUserData['subnets']['privateWebAZ3Id']
        ]

        self.webServerASG = t.add_resource(AutoScalingGroup(
            'WebServerASG',
            LaunchConfigurationName=Ref(self.asgLaunchConfig),
            LoadBalancerNames=[Ref(self.elb)],
            MinSize='1',
            DesiredCapacity='2',
            Cooldown='1',
            MaxSize='5',
            UpdatePolicy = UpdatePolicy(
                    AutoScalingRollingUpdate=AutoScalingRollingUpdate(
                    MinInstancesInService="1"
                )
            ),
            VPCZoneIdentifier=webserverSubnetIds,
            Tags=[
                ASTag('Contact', Ref(self.ownerEmailParam), True),
                ASTag('Name', Join("", [
                    self.namePrefix,
                    'ASG'
                ]), True)
            ]
        ))

        return 0

    def add_outputs(self):
        t = self.template

        self.websiteUrl = t.add_output(Output(
            'websiteUrl',
            Value=Join('', ['http://', GetAtt(self.elb, 'DNSName')]),
            Description='Wordpress website URL.'
        ))

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
