"""
Seed demo data for development and testing.
Creates users, clients, workers, colors, sizes, stages, models, and production records.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import random


class Command(BaseCommand):
    help = 'Seed the database with demo data'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('🌱 Seeding demo data...')

        # Admin user
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@factory.com', 'admin123')
            self.stdout.write('  ✅ Created admin user (admin/admin123)')

        # Staff user
        if not User.objects.filter(username='staff').exists():
            u = User.objects.create_user('staff', 'staff@factory.com', 'staff123')
            u.is_staff = True
            u.save()
            self.stdout.write('  ✅ Created staff user (staff/staff123)')

        from catalog.models import Color, Size, ProductionStage, Client, ProductModel, ProductModelStage
        from workers.models import Worker
        from catalog.services import generate_variants

        # Colors
        colors_data = ['أسود', 'أبيض', 'بيج', 'وردي', 'أزرق', 'أحمر']
        colors = {}
        for name in colors_data:
            c, _ = Color.objects.get_or_create(name=name)
            colors[name] = c
        self.stdout.write(f'  ✅ Colors: {len(colors_data)}')

        # Sizes
        sizes_data = [('75', 0), ('80', 1), ('85', 2), ('90', 3), ('S', 4), ('M', 5), ('L', 6), ('XL', 7)]
        sizes = {}
        for name, order in sizes_data:
            s, _ = Size.objects.get_or_create(name=name, defaults={'sort_order': order})
            sizes[name] = s
        self.stdout.write(f'  ✅ Sizes: {len(sizes_data)}')

        # Production Stages
        stages_data = [
            ('قص', 0), ('خياطة', 1), ('تعبئة', 2), ('تشطيب', 3), ('فحص', 4),
        ]
        stages = {}
        for name, order in stages_data:
            st, _ = ProductionStage.objects.get_or_create(name=name, defaults={'sort_order': order})
            stages[name] = st
        self.stdout.write(f'  ✅ Stages: {len(stages_data)}')

        # Clients
        clients_data = [
            ('CLT-001', 'شركة الأمل للملابس', '01012345678'),
            ('CLT-002', 'مصنع النور', '01098765432'),
            ('CLT-003', 'دار الأزياء الحديثة', '01155554444'),
        ]
        clients = {}
        for code, name, phone in clients_data:
            cl, _ = Client.objects.get_or_create(code=code, defaults={'name': name, 'phone': phone})
            clients[code] = cl
        self.stdout.write(f'  ✅ Clients: {len(clients_data)}')

        # Workers
        workers_data = [
            ('أحمد محمد', '01111111111', ['قص', 'خياطة']),
            ('فاطمة علي', '01222222222', ['خياطة', 'تعبئة']),
            ('محمود حسن', '01333333333', ['قص']),
            ('سارة إبراهيم', '01444444444', ['تشطيب', 'فحص']),
            ('علي عبدالله', '01555555555', ['تعبئة', 'تشطيب']),
        ]
        workers = []
        for name, phone, stage_names in workers_data:
            w, _ = Worker.objects.get_or_create(phone=phone, defaults={'name': name})
            w.stages.set([stages[s] for s in stage_names])
            workers.append(w)
        self.stdout.write(f'  ✅ Workers: {len(workers_data)}')

        # Product Models
        model_configs = [
            {
                'code': 'BR-100',
                'name': 'موديل كلاسيك أسود',
                'client': clients['CLT-001'],
                'colors': ['أسود', 'أبيض'],
                'sizes': ['75', '80', '85'],
                'stages': [('قص', '0.50'), ('خياطة', '1.25'), ('تعبئة', '0.30')],
                'planned': 500,
            },
            {
                'code': 'BR-200',
                'name': 'موديل سبور وردي',
                'client': clients['CLT-002'],
                'colors': ['وردي', 'أزرق'],
                'sizes': ['S', 'M', 'L', 'XL'],
                'stages': [('قص', '0.75'), ('خياطة', '1.50'), ('تشطيب', '0.50'), ('فحص', '0.25')],
                'planned': 300,
            },
        ]

        for cfg in model_configs:
            pm, created = ProductModel.objects.get_or_create(
                code=cfg['code'],
                defaults={
                    'name': cfg['name'],
                    'client': cfg['client'],
                }
            )
            if created:
                pm.colors.set([colors[c] for c in cfg['colors']])
                pm.sizes.set([sizes[s] for s in cfg['sizes']])
                for i, (stage_name, price) in enumerate(cfg['stages']):
                    ProductModelStage.objects.get_or_create(
                        product_model=pm,
                        stage=stages[stage_name],
                        defaults={'unit_price': Decimal(price), 'sort_order': i}
                    )
                created_count, _ = generate_variants(pm)
                # Set planned quantities
                pm.variants.all().update(planned_quantity=cfg['planned'])
                self.stdout.write(f'  ✅ Model {pm.code}: {created_count} variants created')

        # Demo Production Entries
        from production.models import ProductionEntry
        admin_user = User.objects.get(username='admin')

        if ProductionEntry.objects.count() == 0:
            from catalog.models import ProductVariant
            today = timezone.localdate()
            stage_qs = ProductionStage.objects.all()

            for pm in ProductModel.objects.all():
                variants = list(pm.variants.all()[:3])
                model_stages = list(pm.model_stages.filter(is_active=True).select_related('stage'))

                for variant in variants:
                    for ms in model_stages[:2]:
                        stage = ms.stage
                        # Find a worker for this stage
                        worker_qs = Worker.objects.filter(stages=stage, is_active=True)
                        if not worker_qs.exists():
                            continue
                        worker = worker_qs.first()
                        qty = random.randint(50, 150)
                        total = ms.unit_price * qty
                        ProductionEntry.objects.create(
                            variant=variant,
                            stage=stage,
                            worker=worker,
                            quantity=qty,
                            unit_price_snapshot=ms.unit_price,
                            total_amount=total,
                            production_date=today,
                            created_by=admin_user,
                        )
            self.stdout.write('  ✅ Demo production entries created')

        self.stdout.write(self.style.SUCCESS('\n🎉 Seeding complete! Login with admin/admin123'))
