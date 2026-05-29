import { App, Stack } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { ReleasesConfig } from '../lib/config';
import { IamOidcStack } from '../lib/iam-oidc-stack';

function makeStack(): IamOidcStack {
  const app = new App();
  const cfg = new ReleasesConfig({ account: '111122223333', primaryRegion: 'us-east-1' });
  const support = new Stack(app, 'Support', { env: { account: cfg.account, region: cfg.primaryRegion } });
  const bucket = new Bucket(support, 'B', { bucketName: cfg.domainName });
  return new IamOidcStack(app, 'TestIamOidcStack', {
    config: cfg,
    releasesBucket: bucket,
    env: { account: cfg.account, region: cfg.primaryRegion },
  });
}

describe('IamOidcStack', () => {
  test('matches snapshot', () => {
    expect(Template.fromStack(makeStack()).toJSON()).toMatchSnapshot();
  });

  test('creates the GitHub OIDC provider with the correct issuer', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('Custom::AWSCDKOpenIdConnectProvider', {
      Url: 'https://token.actions.githubusercontent.com',
      ClientIDList: ['sts.amazonaws.com'],
    });
  });

  test('creates the gha-locksmith-release-publisher role scoped to the repo', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::IAM::Role', {
      RoleName: 'gha-locksmith-release-publisher',
      AssumeRolePolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Condition: Match.objectLike({
              StringLike: Match.objectLike({
                'token.actions.githubusercontent.com:sub': Match.arrayWith([
                  Match.stringLikeRegexp('repo:seriouscoderone/locksmith:.*'),
                ]),
              }),
            }),
          }),
        ]),
      }),
    });
  });

  test('role policy is scoped to the releases bucket only', () => {
    const t = Template.fromStack(makeStack());
    t.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: Match.arrayWith(['s3:PutObject', 's3:GetObject']),
            Effect: 'Allow',
          }),
        ]),
      }),
    });
  });

  test('uses an existing OIDC provider when existingOidcProviderArn is given', () => {
    const app = new App();
    const cfg = new ReleasesConfig({ account: '111122223333', primaryRegion: 'us-east-1' });
    const support = new Stack(app, 'Support2', { env: { account: cfg.account, region: cfg.primaryRegion } });
    const bucket = new Bucket(support, 'B2', { bucketName: cfg.domainName });
    const stack = new IamOidcStack(app, 'TestImportOidcStack', {
      config: cfg,
      releasesBucket: bucket,
      existingOidcProviderArn: 'arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com',
      env: { account: cfg.account, region: cfg.primaryRegion },
    });
    const t = Template.fromStack(stack);
    // No new OIDC provider should be created in this stack
    t.resourceCountIs('AWS::IAM::OIDCProvider', 0);
    t.resourceCountIs('Custom::AWSCDKOpenIdConnectProvider', 0);
    // The role still exists
    t.hasResourceProperties('AWS::IAM::Role', {
      RoleName: 'gha-locksmith-release-publisher',
    });
  });
});
