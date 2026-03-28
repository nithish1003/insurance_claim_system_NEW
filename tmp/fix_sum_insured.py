from policy.models import UserPolicy

def run():
    print("Migrating sum_insured_remaining...")
    queryset = UserPolicy.objects.filter(sum_insured_remaining__isnull=True)
    count = queryset.count()
    print(f"Found {count} records to fix.")
    for up in queryset:
        up.sum_insured_remaining = up.policy.sum_insured
        up.save(update_fields=['sum_insured_remaining'])
        print(f"Fixed {up.certificate_number}: {up.sum_insured_remaining}")
    print("Done.")

if __name__ == "__main__":
    run()

run()
