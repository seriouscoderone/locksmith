import { Stack, StackProps, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import {
  OpenIdConnectProvider,
  IOpenIdConnectProvider,
  Role,
  WebIdentityPrincipal,
  PolicyStatement,
  Effect,
} from 'aws-cdk-lib/aws-iam';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import { ReleasesConfig } from './config';

export interface IamOidcStackProps extends StackProps {
  readonly config: ReleasesConfig;
  readonly releasesBucket: Bucket;
  /**
   * If set, import the existing GitHub OIDC provider at this ARN instead of creating a new one.
   * AWS only allows one OIDC provider per issuer per account, so set this if the account
   * already has a GitHub OIDC provider from a prior project.
   */
  readonly existingOidcProviderArn?: string;
}

export class IamOidcStack extends Stack {
  public readonly publisherRole: Role;

  constructor(scope: Construct, id: string, props: IamOidcStackProps) {
    super(scope, id, props);

    const provider: IOpenIdConnectProvider = props.existingOidcProviderArn
      ? OpenIdConnectProvider.fromOpenIdConnectProviderArn(this, 'GithubOidc', props.existingOidcProviderArn)
      : new OpenIdConnectProvider(this, 'GithubOidc', {
          url: 'https://token.actions.githubusercontent.com',
          clientIds: ['sts.amazonaws.com'],
        });

    const principal = new WebIdentityPrincipal(provider.openIdConnectProviderArn, {
      StringEquals: {
        'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
      },
      StringLike: {
        'token.actions.githubusercontent.com:sub': [
          `repo:${props.config.githubRepo}:ref:refs/tags/v*`,
          `repo:${props.config.githubRepo}:ref:refs/heads/main`,
          `repo:${props.config.githubRepo}:ref:refs/heads/development`,
          `repo:${props.config.githubRepo}:environment:release`,
        ],
      },
    });

    this.publisherRole = new Role(this, 'PublisherRole', {
      roleName: props.config.iamRoleName,
      assumedBy: principal,
      description: 'GitHub Actions role for uploading Locksmith releases to S3',
    });

    this.publisherRole.addToPolicy(new PolicyStatement({
      effect: Effect.ALLOW,
      actions: [
        's3:PutObject',
        's3:PutObjectAcl',
        's3:GetObject',
        's3:DeleteObject',
        's3:ListBucket',
      ],
      resources: [
        props.releasesBucket.bucketArn,
        `${props.releasesBucket.bucketArn}/*`,
      ],
    }));

    new CfnOutput(this, 'PublisherRoleArn', {
      value: this.publisherRole.roleArn,
      exportName: 'LocksmithPublisherRoleArn',
    });
  }
}
