import { Stack, StackProps, RemovalPolicy, CfnOutput } from 'aws-cdk-lib';
import { Bucket, BlockPublicAccess, BucketEncryption } from 'aws-cdk-lib/aws-s3';
import { OriginAccessIdentity } from 'aws-cdk-lib/aws-cloudfront';
import { Construct } from 'constructs';
import { ReleasesConfig } from './config';

export interface BucketStackProps extends StackProps {
  readonly config: ReleasesConfig;
}

export class BucketStack extends Stack {
  public readonly bucket: Bucket;
  public readonly originAccessIdentity: OriginAccessIdentity;

  constructor(scope: Construct, id: string, props: BucketStackProps) {
    super(scope, id, props);

    this.bucket = new Bucket(this, 'ReleasesBucket', {
      bucketName: props.config.domainName,
      versioned: true,
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      encryption: BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    this.originAccessIdentity = new OriginAccessIdentity(this, 'ReleasesOAI', {
      comment: `OAI for ${props.config.domainName}`,
    });

    this.bucket.grantRead(this.originAccessIdentity);

    new CfnOutput(this, 'ReleasesBucketName', {
      value: this.bucket.bucketName,
      exportName: 'LocksmithReleasesBucketName',
    });

    new CfnOutput(this, 'ReleasesBucketArn', {
      value: this.bucket.bucketArn,
      exportName: 'LocksmithReleasesBucketArn',
    });

    new CfnOutput(this, 'ReleasesOaiId', {
      value: this.originAccessIdentity.originAccessIdentityId,
      exportName: 'LocksmithReleasesOaiId',
    });
  }
}
