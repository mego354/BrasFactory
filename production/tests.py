from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from decimal import Decimal
from catalog.models import Client as FactoryClient, ProductModel, Color, Size, ProductionStage, ProductModelStage, ProductVariant
from catalog.services import generate_variants
from workers.models import Worker
from production.models import ProductionEntry
from production.services import create_production_entry, cancel_production_entry


class FactoryAppTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@factory.com', 'admin123')
        self.client_app = Client()
        self.client_app.login(username='admin', password='admin123')

        self.factory_client = FactoryClient.objects.create(code='CLT-001', name='شركة الأمل', phone='01012345678')
        self.color = Color.objects.create(name='أسود')
        self.size = Size.objects.create(name='75', sort_order=0)
        self.stage = ProductionStage.objects.create(name='خياطة', sort_order=0)

        self.model = ProductModel.objects.create(code='BR-100', name='موديل كلاسيك', client=self.factory_client)
        self.model.colors.add(self.color)
        self.model.sizes.add(self.size)

        self.model_stage = ProductModelStage.objects.create(
            product_model=self.model,
            stage=self.stage,
            unit_price=Decimal('1.50')
        )
        generate_variants(self.model)
        self.variant = ProductVariant.objects.get(product_model=self.model, color=self.color, size=self.size)
        self.variant.planned_quantity = 200
        self.variant.save()

        self.worker = Worker.objects.create(name='أحمد', phone='01111111111')
        self.worker.stages.add(self.stage)

    def test_routes_status_codes(self):
        # Main routes
        routes = [
            'production:dashboard',
            'production:entry',
            'catalog:client_list',
            'catalog:model_list',
            'catalog:settings_index',
            'workers:list',
            'reports:index',
            'reports:by_model',
            'reports:by_worker',
            'reports:by_client',
            'reports:by_stage',
        ]
        for route_name in routes:
            url = reverse(route_name)
            resp = self.client_app.get(url)
            self.assertEqual(resp.status_code, 200, f"Route {route_name} at {url} returned {resp.status_code}")

    def test_clients_url_direct(self):
        resp = self.client_app.get('/clients/')
        self.assertEqual(resp.status_code, 200)

    def test_production_entry_creation_and_cancellation(self):
        entry = create_production_entry(
            variant_id=self.variant.pk,
            stage_id=self.stage.pk,
            worker_id=self.worker.pk,
            quantity=100,
            production_date='2026-08-16',
            user=self.user,
        )
        self.assertEqual(entry.total_amount, Decimal('150.00'))
        self.assertEqual(entry.unit_price_snapshot, Decimal('1.50'))

        # Test cancel
        cancelled = cancel_production_entry(entry, 'خطأ في الإدخال', self.user)
        self.assertTrue(cancelled.is_cancelled)

    def test_cancel_entry_view_post(self):
        entry = create_production_entry(
            variant_id=self.variant.pk,
            stage_id=self.stage.pk,
            worker_id=self.worker.pk,
            quantity=50,
            production_date='2026-08-16',
            user=self.user,
        )
        cancel_url = reverse('production:cancel_entry', kwargs={'pk': entry.pk})
        resp = self.client_app.post(cancel_url)
        self.assertEqual(resp.status_code, 302)
        entry.refresh_from_db()
        self.assertTrue(entry.is_cancelled)

    def test_strict_planned_quantity_enforcement(self):
        from production.services import ProductionValidationError
        # 1. Entry within limit (50 <= 200)
        entry1 = create_production_entry(
            variant_id=self.variant.pk,
            stage_id=self.stage.pk,
            worker_id=self.worker.pk,
            quantity=150,
            production_date='2026-08-16',
            user=self.user,
        )
        self.assertEqual(entry1.quantity, 150)

        # 2. Entry exceeding remaining (150 + 60 = 210 > 200) -> Should fail
        with self.assertRaises(ProductionValidationError):
            create_production_entry(
                variant_id=self.variant.pk,
                stage_id=self.stage.pk,
                worker_id=self.worker.pk,
                quantity=60,
                production_date='2026-08-16',
                user=self.user,
            )

        # 3. Entry exactly at remaining limit (150 + 50 = 200) -> Should succeed
        entry2 = create_production_entry(
            variant_id=self.variant.pk,
            stage_id=self.stage.pk,
            worker_id=self.worker.pk,
            quantity=50,
            production_date='2026-08-16',
            user=self.user,
        )
        self.assertEqual(entry2.quantity, 50)

        # 4. Now stage is at 200/200, any new entry must be rejected
        with self.assertRaises(ProductionValidationError):
            create_production_entry(
                variant_id=self.variant.pk,
                stage_id=self.stage.pk,
                worker_id=self.worker.pk,
                quantity=1,
                production_date='2026-08-16',
                user=self.user,
            )

    def test_zero_planned_quantity_refusal(self):
        from production.services import ProductionValidationError
        self.variant.planned_quantity = 0
        self.variant.save()

        with self.assertRaises(ProductionValidationError):
            create_production_entry(
                variant_id=self.variant.pk,
                stage_id=self.stage.pk,
                worker_id=self.worker.pk,
                quantity=10,
                production_date='2026-08-16',
                user=self.user,
            )

    def test_ajax_cascading_endpoints(self):
        # Models by client
        resp = self.client_app.get(reverse('ajax:models_by_client'), {'client_id': self.factory_client.pk})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['models']), 1)

        # Variants by model
        resp = self.client_app.get(reverse('ajax:variants_by_model'), {'model_id': self.model.pk})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['variants']), 1)

        # Stages by variant
        resp = self.client_app.get(reverse('ajax:stages_by_variant'), {'variant_id': self.variant.pk})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['stages']), 1)

        # Workers by stage
        resp = self.client_app.get(reverse('ajax:workers_by_stage'), {'stage_id': self.stage.pk})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['workers']), 1)

        # Price for stage with remaining quantity
        resp = self.client_app.get(reverse('ajax:price_for_stage'), {'variant_id': self.variant.pk, 'stage_id': self.stage.pk})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['unit_price'], '1.50')
        self.assertEqual(data['planned_quantity'], 200)
        self.assertEqual(data['remaining_quantity'], 200)

    def test_qr_code_routes(self):
        # QR image endpoint
        qr_img_url = reverse('catalog:variant_qr_image', kwargs={'pk': self.variant.pk})
        resp = self.client_app.get(qr_img_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'image/png')

        # QR single card endpoint
        qr_card_url = reverse('catalog:variant_qr_card', kwargs={'pk': self.variant.pk})
        resp = self.client_app.get(qr_card_url)
        self.assertEqual(resp.status_code, 200)

        # Model QR sheet endpoint
        qr_sheet_url = reverse('catalog:model_qr_sheet', kwargs={'pk': self.model.pk})
        resp = self.client_app.get(qr_sheet_url)
        self.assertEqual(resp.status_code, 200)

    def test_qr_prefill_entry_view(self):
        # Entry with variant param
        entry_url = f"{reverse('production:entry')}?variant={self.variant.pk}"
        resp = self.client_app.get(entry_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '⚡ تم التعبئة عبر رمز QR')
        self.assertEqual(resp.context['initial_variant_id'], str(self.variant.pk))
        self.assertEqual(resp.context['initial_client_id'], str(self.factory_client.pk))
        self.assertEqual(resp.context['initial_model_id'], str(self.model.pk))

    def test_staff_entry_post_planned_limit_exceeded(self):
        entry_url = reverse('production:entry')
        post_data = {
            'worker': self.worker.pk,
            'variant': self.variant.pk,
            'stage': self.stage.pk,
            'quantity': 300, # Planned is 200
            'production_date': '2026-08-16',
        }
        resp = self.client_app.post(entry_url, post_data)
        # Should stay on page and render error
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'تتجاوز الكمية المخططة المتبقية')
        # Ensure no entry was created
        self.assertEqual(ProductionEntry.objects.count(), 0)

    def test_worker_entry_post_planned_limit_exceeded(self):
        # Log out django user to simulate worker-only session
        self.client_app.logout()

        session = self.client_app.session
        session['external_auth'] = {'type': 'worker', 'entity_id': self.worker.pk}
        session.save()

        entry_url = reverse('production:entry')
        post_data = {
            'variant': self.variant.pk,
            'stage': self.stage.pk,
            'quantity': 250, # Planned is 200
            'production_date': '2026-08-16',
        }
        resp = self.client_app.post(entry_url, post_data, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'تتجاوز الكمية المخططة المتبقية')
        self.assertEqual(ProductionEntry.objects.count(), 0)


