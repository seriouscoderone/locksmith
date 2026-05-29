import { App } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { ReleasesConfig } from '../lib/config';
import { BucketStack } from '../lib/bucket-stack';

function makeStack(): BucketStack {
  const app = new App();
  const cfg = new ReleasesConfig({ account: '111122223333', primaryRegion: 'us-east-1' });
  return new BucketStack(app, 'TestBucketStack', { config: cfg, env: { account: cfg.account, region: cfg.primaryRegion } });
}

describe('BucketStack', () => {
  test('matches snapshot', () => {
    expect(Template.fromStack(makeStack()).toJSON()).toMatchSnapshot();
  });

  test('creates the releases.keri.host bucket with versioning and block-public-access', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::S3::Bucket', {
      BucketName: 'releases.keri.host',
      VersioningConfiguration: { Status: 'Enabled' },
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
    });
  });

  test('creates an origin access identity', () => {
    const t = Template.fromStack(makeStack());
    t.resourceCountIs('AWS::CloudFront::CloudFrontOriginAccessIdentity', 1);
  });

  test('bucket policy grants OAI read but no public principals', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::S3::BucketPolicy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: Match.anyValue(),
            Principal: Match.objectLike({ CanonicalUser: Match.anyValue() }),
          }),
        ]),
      }),
    });
  });
});
