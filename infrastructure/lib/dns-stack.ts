import { Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { ARecord, AaaaRecord, HostedZone, RecordTarget } from 'aws-cdk-lib/aws-route53';
import { CloudFrontTarget } from 'aws-cdk-lib/aws-route53-targets';
import { IDistribution } from 'aws-cdk-lib/aws-cloudfront';
import { ReleasesConfig } from './config';

export interface DnsStackProps extends StackProps {
  readonly config: ReleasesConfig;
  readonly distribution: IDistribution;
}

export class DnsStack extends Stack {
  constructor(scope: Construct, id: string, props: DnsStackProps) {
    super(scope, id, props);

    const zone = HostedZone.fromLookup(this, 'ParentZone', {
      domainName: props.config.parentZone,
    });

    const target = RecordTarget.fromAlias(new CloudFrontTarget(props.distribution));

    new ARecord(this, 'ReleasesA', {
      zone,
      recordName: 'releases',
      target,
    });

    new AaaaRecord(this, 'ReleasesAAAA', {
      zone,
      recordName: 'releases',
      target,
    });
  }
}
