import { App, Stack } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { OriginAccessIdentity } from 'aws-cdk-lib/aws-cloudfront';
import { Certificate } from 'aws-cdk-lib/aws-certificatemanager';
import { ReleasesConfig } from '../lib/config';
import { CdnStack } from '../lib/cdn-stack';

function makeStack(): CdnStack {
  const app = new App();
  const cfg = new ReleasesConfig({ account: '111122223333', primaryRegion: 'us-east-1' });
  const supportStack = new Stack(app, 'Support', { env: { account: cfg.account, region: cfg.primaryRegion } });
  const bucket = new Bucket(supportStack, 'B', { bucketName: cfg.domainName });
  const oai = new OriginAccessIdentity(supportStack, 'O');
  const cert = Certificate.fromCertificateArn(supportStack, 'C', 'arn:aws:acm:us-east-1:111122223333:certificate/abc');
  return new CdnStack(app, 'TestCdnStack', {
    config: cfg,
    bucket,
    originAccessIdentity: oai,
    certificate: cert,
    env: { account: cfg.account, region: cfg.primaryRegion },
  });
}

describe('CdnStack', () => {
  test('matches snapshot', () => {
    expect(Template.fromStack(makeStack()).toJSON()).toMatchSnapshot();
  });

  test('uses HTTP/2 + HTTP/3 and TLS 1.2+', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: Match.objectLike({
        HttpVersion: 'http2and3',
        ViewerCertificate: Match.objectLike({ MinimumProtocolVersion: Match.stringLikeRegexp('TLSv1.2_2021') }),
        Aliases: ['releases.keri.host'],
      }),
    });
  });

  test('defines three cache behaviors with correct TTLs', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: Match.objectLike({
        CacheBehaviors: Match.arrayWith([
          Match.objectLike({ PathPattern: 'releases/*' }),
          Match.objectLike({ PathPattern: 'appcast/*' }),
          Match.objectLike({ PathPattern: 'publisher/*' }),
        ]),
      }),
    });
  });

  test('declares a 404 custom error response', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::CloudFront::Distribution', {
      DistributionConfig: Match.objectLike({
        CustomErrorResponses: Match.arrayWith([
          Match.objectLike({ ErrorCode: 404, ResponsePagePath: '/404.html' }),
        ]),
      }),
    });
  });
});
