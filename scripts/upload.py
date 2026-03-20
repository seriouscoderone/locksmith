import boto3
import argparse


def upload(accessKey, secretKey, region, bucket, objectKey, file):
    # DigitalOcean Spaces credentials

    # Initialize the S3 client
    s3 = boto3.client(
        's3',
        region_name=region,
        endpoint_url=f'https://{region}.digitaloceanspaces.com',
        aws_access_key_id=accessKey,
        aws_secret_access_key=secretKey
    )

    try:
        s3.upload_file(file, bucket, objectKey)
        print(f"File '{objectKey}' uploaded successfully.")

    except Exception as e:
        print(f"Error uploading file: {e}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upload a file')
    parser.add_argument('--access-key', required=True,
                        help='the path to workspace')
    parser.add_argument('--secret-key', required=True,
                        help='path to schema')
    parser.add_argument('--region', required=True,
                        help='path to dem')
    parser.add_argument('--bucket', required=True,
                        help='path to dem')
    parser.add_argument('--object-key', required=True,
                        help='path to dem')
    parser.add_argument('--file', required=True,
                        help='path to dem')
    args = parser.parse_args()
    upload(args.access_key, args.secret_key, args.region, args.bucket, args.object_key, args.file)