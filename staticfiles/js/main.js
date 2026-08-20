/**
 * Factory Management System — Global JavaScript
 * AJAX helpers, cascading dropdowns, UI interactions & QR prefilling
 */

// ============================================================
// CSRF Helper
// ============================================================
function getCsrfToken() {
  return document.cookie.split(';')
    .find(c => c.trim().startsWith('csrftoken='))
    ?.split('=')[1] || '';
}

// ============================================================
// AJAX GET helper
// ============================================================
async function ajaxGet(url, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const fullUrl = qs ? `${url}?${qs}` : url;
  const resp = await fetch(fullUrl, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// ============================================================
// AJAX POST helper
// ============================================================
async function ajaxPost(url, data = {}) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken(),
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// ============================================================
// Populate a <select> element
// ============================================================
function populateSelect(selectEl, items, placeholder = 'اختر...', valueKey = 'id', labelKey = 'name') {
  if (!selectEl) return;
  selectEl.innerHTML = `<option value="">${placeholder}</option>`;
  if (items && items.length > 0) {
    items.forEach(item => {
      const opt = document.createElement('option');
      opt.value = item[valueKey];
      opt.textContent = item[labelKey];
      selectEl.appendChild(opt);
    });
    selectEl.disabled = false;
  } else {
    selectEl.disabled = true;
  }
}

// ============================================================
// Show / hide a loading spinner inside a select
// ============================================================
function setSelectLoading(selectEl, loading) {
  if (!selectEl) return;
  if (loading) {
    selectEl.disabled = true;
    selectEl.innerHTML = '<option value="">جاري التحميل...</option>';
  }
}

// ============================================================
// Django Messages auto-dismiss & Mobile Sidebar
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.alert[data-autodismiss]').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity 0.5s ease';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    }, 4000);
  });

  // Mobile sidebar toggle & keyboard/touch accessibility
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');

  function closeSidebar() {
    sidebar?.classList.remove('open');
    overlay?.classList.remove('visible');
    document.body.style.overflow = '';
  }

  function openSidebar() {
    sidebar?.classList.add('open');
    overlay?.classList.add('visible');
    if (window.innerWidth <= 1024) {
      document.body.style.overflow = 'hidden'; // Prevent background scrolling when drawer is open
    }
  }

  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
    });
    sidebarCloseBtn?.addEventListener('click', closeSidebar);
    overlay?.addEventListener('click', closeSidebar);

    // Auto-close sidebar on mobile when navigating
    document.querySelectorAll('.sidebar-item').forEach(link => {
      link.addEventListener('click', () => {
        if (window.innerWidth <= 1024) {
          closeSidebar();
        }
      });
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeSidebar();
    });
  }

});

// ============================================================
// Production Entry — Cascading Dropdowns & QR Pre-filling
// ============================================================
function initProductionEntry() {
  const formEl      = document.getElementById('productionForm');
  if (!formEl || document.getElementById('worker_search_input') || document.getElementById('workerProductionForm')) {
    return;
  }
  const selClient   = document.getElementById('id_client');
  const selModel    = document.getElementById('id_product_model');
  const selVariant  = document.getElementById('id_variant');
  const selStage    = document.getElementById('id_stage');
  const selWorker   = document.getElementById('id_worker');
  const fldPrice    = document.getElementById('id_unit_price_display');
  const fldQty      = document.getElementById('id_quantity');
  const fldTotal    = document.getElementById('id_total_display');
  const hidPrice    = document.getElementById('id_unit_price_hidden');

  if (!selClient) return;

  function clearPrice() {
    if (fldPrice) fldPrice.textContent = '—';
    if (fldTotal) fldTotal.textContent = '—';
    if (hidPrice) hidPrice.value = '';
  }

  function updateTotal() {
    const qty = parseFloat(fldQty?.value) || 0;
    const price = parseFloat(hidPrice?.value) || 0;
    if (fldTotal) {
      if (qty > 0 && price > 0) {
        const total = qty * price;
        fldTotal.textContent = total.toFixed(2) + ' ج.م';
      } else {
        fldTotal.textContent = '—';
      }
    }
  }

  // Client → Models
  selClient.addEventListener('change', async () => {
    const clientId = selClient.value;
    [selModel, selVariant, selStage, selWorker].forEach(s => {
      if (s) { s.innerHTML = '<option value="">اختر...</option>'; s.disabled = true; }
    });
    clearPrice();
    if (!clientId) return;

    setSelectLoading(selModel, true);
    try {
      const data = await ajaxGet('/ajax/models-by-client/', { client_id: clientId });
      if (data.models && data.models.length > 0) {
        populateSelect(selModel, data.models, 'اختر الموديل...');
        if (data.models.length === 1) {
          selModel.value = data.models[0].id;
          selModel.dispatchEvent(new Event('change'));
        }
      } else {
        populateSelect(selModel, [], '⚠️ لا توجد موديلات لهذا العميل');
      }
    } catch (e) {
      console.error(e);
      selModel.innerHTML = '<option value="">خطأ في تحميل الموديلات</option>';
      selModel.disabled = true;
    }
  });

  // Model → Variants
  selModel?.addEventListener('change', async () => {
    const modelId = selModel.value;
    [selVariant, selStage, selWorker].forEach(s => {
      if (s) { s.innerHTML = '<option value="">اختر...</option>'; s.disabled = true; }
    });
    clearPrice();
    if (!modelId) return;

    setSelectLoading(selVariant, true);
    try {
      const data = await ajaxGet('/ajax/variants-by-model/', { model_id: modelId });
      if (data.variants && data.variants.length > 0) {
        populateSelect(selVariant, data.variants, 'اختر نوع المنتج (اللون / المقاس)...');
        if (data.variants.length === 1) {
          selVariant.value = data.variants[0].id;
          selVariant.dispatchEvent(new Event('change'));
        }
      } else {
        populateSelect(selVariant, [], '⚠️ لا توجد أنواع لهذا الموديل');
      }
    } catch (e) {
      console.error(e);
      selVariant.innerHTML = '<option value="">خطأ في التحميل</option>';
      selVariant.disabled = true;
    }
  });

  // Variant → Stages
  selVariant?.addEventListener('change', async () => {
    const variantId = selVariant.value;
    [selStage, selWorker].forEach(s => {
      if (s) { s.innerHTML = '<option value="">اختر...</option>'; s.disabled = true; }
    });
    clearPrice();
    if (!variantId) return;

    setSelectLoading(selStage, true);
    try {
      const data = await ajaxGet('/ajax/stages-by-variant/', { variant_id: variantId });
      if (data.stages && data.stages.length > 0) {
        populateSelect(selStage, data.stages, 'اختر مرحلة الإنتاج...');
        if (data.stages.length === 1) {
          selStage.value = data.stages[0].id;
          selStage.dispatchEvent(new Event('change'));
        }
      } else {
        populateSelect(selStage, [], '⚠️ لا توجد مراحل مهيأة لهذا الموديل');
      }
    } catch (e) {
      console.error(e);
      selStage.innerHTML = '<option value="">خطأ في التحميل</option>';
      selStage.disabled = true;
    }
  });

  // Stage → Workers + Price
  selStage?.addEventListener('change', async () => {
    const stageId = selStage.value;
    const variantId = selVariant?.value;
    if (selWorker) { selWorker.innerHTML = '<option value="">اختر...</option>'; selWorker.disabled = true; }
    clearPrice();
    if (!stageId) return;

    // Load workers
    setSelectLoading(selWorker, true);
    try {
      const data = await ajaxGet('/ajax/workers-by-stage/', { stage_id: stageId });
      if (data.workers && data.workers.length > 0) {
        populateSelect(selWorker, data.workers, 'اختر العامل...');
        if (data.workers.length === 1) {
          selWorker.value = data.workers[0].id;
        }
      } else {
        populateSelect(selWorker, [], '⚠️ لا يوجد عمال مسندين لهذه المرحلة');
      }
    } catch (e) {
      console.error(e);
      selWorker.innerHTML = '<option value="">خطأ في التحميل</option>';
      selWorker.disabled = true;
    }

    // Load price
    if (variantId) {
      try {
        const data = await ajaxGet('/ajax/price-for-stage/', { variant_id: variantId, stage_id: stageId });
        const unitPrice = parseFloat(data.unit_price) || 0;
        if (fldPrice) fldPrice.textContent = unitPrice.toFixed(2) + ' ج.م';
        if (hidPrice) hidPrice.value = data.unit_price;
        updateTotal();
      } catch (e) { console.error(e); }
    }
  });

  // Quantity → Total
  fldQty?.addEventListener('input', updateTotal);

  // ============================================================
  // Auto Pre-fill Trigger from Dataset / Query Params (QR Code)
  // ============================================================
  const initialClient  = formEl?.dataset?.initialClient || '';
  const initialModel   = formEl?.dataset?.initialModel || '';
  const initialVariant = formEl?.dataset?.initialVariant || '';

  if (initialClient) {
    selClient.value = initialClient;
    (async () => {
      setSelectLoading(selModel, true);
      try {
        const modelData = await ajaxGet('/ajax/models-by-client/', { client_id: initialClient });
        populateSelect(selModel, modelData.models, 'اختر الموديل...');
        if (initialModel && modelData.models.some(m => String(m.id) === String(initialModel))) {
          selModel.value = initialModel;
        } else if (modelData.models.length === 1) {
          selModel.value = modelData.models[0].id;
        }

        const activeModelId = selModel.value;
        if (activeModelId) {
          setSelectLoading(selVariant, true);
          const varData = await ajaxGet('/ajax/variants-by-model/', { model_id: activeModelId });
          populateSelect(selVariant, varData.variants, 'اختر نوع المنتج (اللون / المقاس)...');
          if (initialVariant && varData.variants.some(v => String(v.id) === String(initialVariant))) {
            selVariant.value = initialVariant;
          } else if (varData.variants.length === 1) {
            selVariant.value = varData.variants[0].id;
          }

          const activeVariantId = selVariant.value;
          if (activeVariantId) {
            setSelectLoading(selStage, true);
            const stageData = await ajaxGet('/ajax/stages-by-variant/', { variant_id: activeVariantId });
            populateSelect(selStage, stageData.stages, 'اختر مرحلة الإنتاج...');
            if (stageData.stages.length === 1) {
              selStage.value = stageData.stages[0].id;
              selStage.dispatchEvent(new Event('change'));
            }
          }
        }
      } catch (e) {
        console.error('Error during initial pre-fill:', e);
      }
    })();
  }
}

// ============================================================
// Confirm delete / cancel dialogs
// ============================================================
function confirmAction(message, formId) {
  if (confirm(message)) {
    document.getElementById(formId)?.submit();
  }
}

// ============================================================
// Filter form auto-submit on select change
// ============================================================
function initAutoSubmitFilters() {
  document.querySelectorAll('[data-auto-submit]').forEach(el => {
    el.addEventListener('change', () => {
      el.closest('form')?.submit();
    });
  });
}

// ============================================================
// Initialize all components
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  initProductionEntry();
  initAutoSubmitFilters();
});
