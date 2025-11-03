aws lambda invoke   --function-name lambda-update   --payload '{"file_path":"Book2.xlsx","dry_run":true}'   --cli-binary-format raw-in-base64-out   response.json && cat response.json
