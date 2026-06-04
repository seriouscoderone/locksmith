import { App, Stack } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { Distribution, OriginAccessIdentity } from 'aws-cdk-lib/aws-cloudfront';
import { S3Origin } from 'aws-cdk-lib/aws-cloudfront-origins';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { ReleasesConfig } from '../lib/config';
import { DnsStack } from '../lib/dns-stack';

function makeStack(): DnsStack {
  const app = new App();
  const cfg = new ReleasesConfig({ account: '111122223333', primaryRegion: 'us-east-1' });
  const supportStack = new Stack(app, 'Support', { env: { account: cfg.account, region: cfg.primaryRegion } });
  const bucket = new Bucket(supportStack, 'B', { bucketName: cfg.domainName });
  const oai = new OriginAccessIdentity(supportStack, 'O');
  const dist = new Distribution(supportStack, 'D', {
    defaultBehavior: { origin: new S3Origin(bucket, { originAccessIdentity: oai }) },
  });
  return new DnsStack(app, 'TestDnsStack', {
    config: cfg,
    distribution: dist,
    env: { account: cfg.account, region: cfg.primaryRegion },
  });
}

describe('DnsStack', () => {
  test('matches snapshot', () => {
    expect(Template.fromStack(makeStack()).toJSON()).toMatchSnapshot();
  });

  test('creates A and AAAA alias records for releases.keri.host', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::Route53::RecordSet', {
      Name: 'releases.keri.host.',
      Type: 'A',
    });
    t.hasResourceProperties('AWS::Route53::RecordSet', {
      Name: 'releases.keri.host.',
      Type: 'AAAA',
    });
  });
});
