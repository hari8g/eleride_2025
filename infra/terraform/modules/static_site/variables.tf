variable "name" {
  type        = string
  description = "Name prefix (used in bucket + distribution)."
}

variable "tags" {
  type        = map(string)
  description = "Common tags."
  default     = {}
}

variable "index_document" {
  type        = string
  default     = "index.html"
}


