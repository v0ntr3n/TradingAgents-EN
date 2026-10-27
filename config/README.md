# Config Directory

This directory is used to store configuration files and usage statistics for TradingAgents.

## File Descriptions

- `usage.json` - Token usage statistics (auto-generated)
- `models.json` - Model configuration file (auto-generated)
- `pricing.json` - Pricing configuration file (auto-generated)
- `settings.json` - System settings file (auto-generated)

## Important Notes

⚠️ **Data Persistence**: This directory is configured as a volume mount in Docker Compose to ensure configuration and usage statistics are not lost when containers restart.

🔒 **Security Reminder**: This directory may contain sensitive usage statistics. Do not commit its contents to public code repositories.

## Backup Recommendations

It is recommended to back up important configuration files in this directory regularly, especially:
- `usage.json` - Contains complete token usage history
- `settings.json` - Contains personalized settings

## Troubleshooting

If you encounter configuration issues:
1. Check whether file permissions are correct
2. Verify that the Docker volume mount is working properly
3. Check the application logs for detailed error messages
