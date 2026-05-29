import { Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Certificate, CertificateValidation } from 'aws-cdk-lib/aws-certificatemanager';
import { HostedZone } from 'aws-cdk-lib/aws-route53';
import { Construct } from 'constructs';
import { ReleasesConfig } from './config';

export interface CertStackProps extends StackProps {
  readonly config: ReleasesConfig;
}

export class CertStack extends Stack {
  public readonly certificateArn: string;

  constructor(scope: Construct, id: string, props: CertStackProps) {
    super(scope, id, props);

    const zone = HostedZone.fromLookup(this, 'ParentZone', {
      domainName: props.config.parentZone,
    });

    const cert = new Certificate(this, 'ReleasesCertificate', {
      domainName: props.config.domainName,
      validation: CertificateValidation.fromDns(zone),
    });

    this.certificateArn = cert.certificateArn;

    new CfnOutput(this, 'CertificateArn', {
      value: cert.certificateArn,
      exportName: 'LocksmithReleasesCertificateArn',
    });
  }
}
