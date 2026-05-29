export interface ReleasesConfigOptions {
  account: string;
  primaryRegion: string;
}

export class ReleasesConfig {
  public static readonly DOMAIN_NAME = 'releases.keri.host';
  public static readonly PARENT_ZONE = 'keri.host';
  public static readonly GITHUB_REPO = 'seriouscoderone/locksmith';
  public static readonly IAM_ROLE_NAME = 'gha-locksmith-release-publisher';
  public static readonly CLOUDFRONT_REGION = 'us-east-1';

  public readonly account: string;
  public readonly primaryRegion: string;
  public readonly cloudfrontRegion: string;
  public readonly domainName: string;
  public readonly parentZone: string;
  public readonly githubRepo: string;
  public readonly iamRoleName: string;

  constructor(opts: ReleasesConfigOptions) {
    this.account = opts.account;
    this.primaryRegion = opts.primaryRegion;
    this.cloudfrontRegion = ReleasesConfig.CLOUDFRONT_REGION;
    this.domainName = ReleasesConfig.DOMAIN_NAME;
    this.parentZone = ReleasesConfig.PARENT_ZONE;
    this.githubRepo = ReleasesConfig.GITHUB_REPO;
    this.iamRoleName = ReleasesConfig.IAM_ROLE_NAME;
  }

  public static fromEnv(): ReleasesConfig {
    const account = process.env.LOCKSMITH_AWS_ACCOUNT;
    const region = process.env.LOCKSMITH_AWS_REGION ?? 'us-east-1';
    if (!account) {
      throw new Error('LOCKSMITH_AWS_ACCOUNT environment variable must be set');
    }
    return new ReleasesConfig({ account, primaryRegion: region });
  }
}
