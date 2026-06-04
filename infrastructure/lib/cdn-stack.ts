import { Stack, StackProps, Duration, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import {
  Distribution,
  ViewerProtocolPolicy,
  HttpVersion,
  SecurityPolicyProtocol,
  AllowedMethods,
  CachedMethods,
  CachePolicy,
  PriceClass,
  OriginAccessIdentity,
  ErrorResponse,
} from 'aws-cdk-lib/aws-cloudfront';
import { S3Origin } from 'aws-cdk-lib/aws-cloudfront-origins';
import { ICertificate } from 'aws-cdk-lib/aws-certificatemanager';
import { BucketDeployment, Source } from 'aws-cdk-lib/aws-s3-deployment';
import * as path from 'path';
import { ReleasesConfig } from './config';

export interface CdnStackProps extends StackProps {
  readonly config: ReleasesConfig;
  readonly bucket: Bucket;
  readonly originAccessIdentity: OriginAccessIdentity;
  readonly certificate: ICertificate;
}

export class CdnStack extends Stack {
  public readonly distribution: Distribution;

  constructor(scope: Construct, id: string, props: CdnStackProps) {
    super(scope, id, props);

    const origin = new S3Origin(props.bucket, {
      originAccessIdentity: props.originAccessIdentity,
    });

    const longTtlPolicy = new CachePolicy(this, 'ImmutableArtifactCachePolicy', {
      cachePolicyName: 'LocksmithReleasesImmutable',
      defaultTtl: Duration.days(365),
      minTtl: Duration.days(365),
      maxTtl: Duration.days(3650),
      enableAcceptEncodingGzip: false,
      enableAcceptEncodingBrotli: false,
    });

    const shortTtlPolicy = new CachePolicy(this, 'ShortLivedCachePolicy', {
      cachePolicyName: 'LocksmithReleasesShortLived',
      defaultTtl: Duration.seconds(60),
      minTtl: Duration.seconds(0),
      maxTtl: Duration.seconds(60),
      enableAcceptEncodingGzip: true,
      enableAcceptEncodingBrotli: true,
    });

    const errorResponses: ErrorResponse[] = [
      {
        httpStatus: 404,
        responseHttpStatus: 404,
        responsePagePath: '/404.html',
        ttl: Duration.seconds(60),
      },
    ];

    this.distribution = new Distribution(this, 'ReleasesDistribution', {
      domainNames: [props.config.domainName],
      certificate: props.certificate,
      defaultBehavior: {
        origin,
        viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: shortTtlPolicy,
        allowedMethods: AllowedMethods.ALLOW_GET_HEAD,
        cachedMethods: CachedMethods.CACHE_GET_HEAD,
      },
      additionalBehaviors: {
        'releases/*': {
          origin,
          viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: longTtlPolicy,
          allowedMethods: AllowedMethods.ALLOW_GET_HEAD,
        },
        'appcast/*': {
          origin,
          viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: shortTtlPolicy,
          allowedMethods: AllowedMethods.ALLOW_GET_HEAD,
        },
        'publisher/*': {
          origin,
          viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          cachePolicy: shortTtlPolicy,
          allowedMethods: AllowedMethods.ALLOW_GET_HEAD,
        },
      },
      httpVersion: HttpVersion.HTTP2_AND_3,
      minimumProtocolVersion: SecurityPolicyProtocol.TLS_V1_2_2021,
      priceClass: PriceClass.PRICE_CLASS_100,
      errorResponses,
      defaultRootObject: '',
      comment: 'Locksmith releases distribution',
    });

    new BucketDeployment(this, 'Deploy404', {
      destinationBucket: props.bucket,
      sources: [Source.asset(path.join(__dirname, '..', 'assets'))],
      retainOnDelete: false,
      prune: false,
    });

    new CfnOutput(this, 'DistributionId', {
      value: this.distribution.distributionId,
      exportName: 'LocksmithReleasesDistributionId',
    });

    new CfnOutput(this, 'DistributionDomainName', {
      value: this.distribution.distributionDomainName,
      exportName: 'LocksmithReleasesDistributionDomain',
    });
  }
}
