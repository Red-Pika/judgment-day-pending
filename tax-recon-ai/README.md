# Terraform Compute

Kode Terraform siap dipakai. Setiap folder adalah stack terpisah.

| Folder | Isi |
|---|---|
| `aws-ec2-vm` | Virtual machine EC2 (tipe, CPU/RAM via instance type, disk, lifecycle) |
| `aws-autoscaling-group` | Launch template + ASG + target tracking CPU |
| `azure-linux-vm` | Azure Linux VM + disk + lifecycle |
| `azure-vm-scale-set` | VM Scale Set + autoscale CPU |
| `gcp-compute-instance` | Google Compute Engine VM |
| `gcp-mig-autoscaler` | Instance template + MIG + autoscaler |

## Cara pakai (satu folder)

```bash
cd terraform/aws-ec2-vm
cp terraform.tfvars.example terraform.tfvars
# isi nilai di terraform.tfvars
terraform init
terraform plan
terraform apply
```

Login cloud dulu:

- AWS: `aws configure` atau env `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
- Azure: `az login`
- GCP: `gcloud auth application-default login` dan set `project_id`

Jangan commit `terraform.tfvars` atau `*.tfstate`.
