module "rider_app_site" {
  source = "./modules/static_site"
  name   = "${var.name}-rider-app"
  tags   = local.common_tags
}

# Repeat these modules for other apps:
#
# module "fleet_portal_site" {
#   source = "./modules/static_site"
#   name   = "${var.name}-fleet-portal"
#   tags   = local.common_tags
# }
#
# module "maintenance_tech_site" {
#   source = "./modules/static_site"
#   name   = "${var.name}-maintenance-tech"
#   tags   = local.common_tags
# }
#
# module "financing_portal_site" {
#   source = "./modules/static_site"
#   name   = "${var.name}-financing-portal"
#   tags   = local.common_tags
# }
#
# module "matchmaking_portal_site" {
#   source = "./modules/static_site"
#   name   = "${var.name}-matchmaking-portal"
#   tags   = local.common_tags
# }


