import React, { useState, useEffect, useRef } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Bar } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

interface ChartDataPoint {
  timestamp: string;
  label: string;
  received: number;
  sent: number;
  total: number;
}

interface TrafficChartCardProps {
  chartData: {
    '6hours': ChartDataPoint[];
    'day': ChartDataPoint[];
    'week': ChartDataPoint[];
    'month': ChartDataPoint[];
  };
  vpn_key_id?: number;
  user_id?: number;
  onFilterChange?: (vpn_key_id?: number, user_id?: number) => void;
}

const TrafficChartCard: React.FC<TrafficChartCardProps> = ({ 
  chartData, 
  vpn_key_id, 
  user_id,
  onFilterChange 
}) => {
  const [selectedPeriod, setSelectedPeriod] = useState<'6hours' | 'day' | 'week' | 'month'>('6hours');
  const [chartMode, setChartMode] = useState<'grouped' | 'stacked'>('grouped');
  const chartRef = useRef<any>(null);
  
  // Сбрасываем фильтр при изменении периода
  useEffect(() => {
    if (onFilterChange && (vpn_key_id || user_id)) {
      // Можно оставить фильтр или сбросить - пока оставляем
    }
  }, [selectedPeriod]);

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const currentData = chartData[selectedPeriod] || [];

  // Создаем градиенты для столбцов
  const createGradient = (ctx: CanvasRenderingContext2D, chartArea: any, color1: string, color2: string) => {
    if (!chartArea) return color1;
    const gradient = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
    gradient.addColorStop(0, color2);
    gradient.addColorStop(1, color1);
    return gradient;
  };

  const chartDataConfig = {
    labels: currentData.map(item => item.label),
    datasets: [
      {
        label: '⬇️ Входящий',
        data: currentData.map(item => item.received),
        backgroundColor: (context: any) => {
          const chart = context.chart;
          const { ctx, chartArea } = chart;
          return createGradient(
            ctx,
            chartArea,
            'rgba(59, 130, 246, 0.9)',  // Синий сверху
            'rgba(59, 130, 246, 0.4)'   // Светло-синий снизу
          );
        },
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 2,
        borderRadius: 6,
        borderSkipped: false,
      },
      {
        label: '⬆️ Исходящий',
        data: currentData.map(item => item.sent),
        backgroundColor: (context: any) => {
          const chart = context.chart;
          const { ctx, chartArea } = chart;
          return createGradient(
            ctx,
            chartArea,
            'rgba(239, 68, 68, 0.9)',   // Красный сверху
            'rgba(239, 68, 68, 0.4)'    // Светло-красный снизу
          );
        },
        borderColor: 'rgba(239, 68, 68, 1)',
        borderWidth: 2,
        borderRadius: 6,
        borderSkipped: false,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    animation: {
      duration: 750,
      easing: 'easeInOutQuart' as const,
    },
    plugins: {
      legend: {
        position: 'top' as const,
        labels: {
          usePointStyle: true,
          padding: 15,
          font: {
            size: 13,
            weight: 'normal' as const,
          },
          color: '#2c3e50',
        },
        onClick: (e: any, legendItem: any) => {
          // Разрешаем скрытие/показ серий по клику на легенду
        },
      },
      title: {
        display: false, // Убираем заголовок, так как он уже есть в header
      },
      tooltip: {
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        padding: 12,
        titleFont: {
          size: 14,
          weight: 'bold' as const,
        },
        bodyFont: {
          size: 13,
        },
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1,
        cornerRadius: 8,
        displayColors: true,
        callbacks: {
          title: function(context: any) {
            return context[0].label;
          },
          label: function(context: any) {
            const value = context.parsed.y;
            const datasetLabel = context.dataset.label.replace(/[⬇️⬆️]/g, '').trim();
            return `${datasetLabel}: ${formatBytes(value)}`;
          },
          footer: function(tooltipItems: any) {
            // Показываем общий трафик в footer
            const total = tooltipItems.reduce((sum: number, item: any) => {
              return sum + (item.parsed.y || 0);
            }, 0);
            return `Всего: ${formatBytes(total)}`;
          },
        },
      },
    },
    scales: {
      x: {
        stacked: chartMode === 'stacked',
        grid: {
          display: false,
        },
        ticks: {
          font: {
            size: 11,
          },
          color: '#7f8c8d',
          maxRotation: 45,
          minRotation: 0,
        },
      },
      y: {
        beginAtZero: true,
        stacked: chartMode === 'stacked',
        grid: {
          color: 'rgba(0, 0, 0, 0.05)',
          drawBorder: false,
        },
        ticks: {
          callback: function(value: any) {
            return formatBytes(value);
          },
          font: {
            size: 11,
          },
          color: '#7f8c8d',
          padding: 10,
        },
      },
    },
  };

  // Вычисляем статистику для отображения
  const totalReceived = currentData.reduce((sum, item) => sum + item.received, 0);
  const totalSent = currentData.reduce((sum, item) => sum + item.sent, 0);
  const totalTraffic = totalReceived + totalSent;
  const avgTraffic = currentData.length > 0 ? totalTraffic / currentData.length : 0;

  return (
    <div className="traffic-chart-card">
      <div className="chart-card-header">
        <div className="chart-header-left">
          <h3>📈 Трафик по периодам</h3>
          {currentData.length > 0 && (
            <div className="chart-stats">
              <span className="stat-item">
                <span className="stat-label">Всего:</span>
                <span className="stat-value">{formatBytes(totalTraffic)}</span>
              </span>
              <span className="stat-item">
                <span className="stat-label">Среднее:</span>
                <span className="stat-value">{formatBytes(avgTraffic)}</span>
              </span>
            </div>
          )}
        </div>
        <div className="chart-controls">
          <div className="chart-mode-selector">
            <button
              className={chartMode === 'grouped' ? 'active' : ''}
              onClick={() => setChartMode('grouped')}
              title="Группированные столбцы"
            >
              📊 Группы
            </button>
            <button
              className={chartMode === 'stacked' ? 'active' : ''}
              onClick={() => setChartMode('stacked')}
              title="Сложенные столбцы"
            >
              📚 Стеки
            </button>
          </div>
          <div className="chart-period-selector">
            <button
              className={selectedPeriod === '6hours' ? 'active' : ''}
              onClick={() => setSelectedPeriod('6hours')}
            >
              6 часов
            </button>
            <button
              className={selectedPeriod === 'day' ? 'active' : ''}
              onClick={() => setSelectedPeriod('day')}
            >
              Сутки
            </button>
            <button
              className={selectedPeriod === 'week' ? 'active' : ''}
              onClick={() => setSelectedPeriod('week')}
            >
              Неделя
            </button>
            <button
              className={selectedPeriod === 'month' ? 'active' : ''}
              onClick={() => setSelectedPeriod('month')}
            >
              Месяц
            </button>
          </div>
        </div>
      </div>
      <div className="chart-container">
        {currentData.length > 0 ? (
          <Bar 
            ref={chartRef}
            data={chartDataConfig} 
            options={chartOptions}
            key={`${selectedPeriod}-${chartMode}`} // Пересоздаем график при изменении периода/режима
          />
        ) : (
          <div className="chart-empty">
            <div className="chart-empty-icon">📊</div>
            <div className="chart-empty-text">Нет данных за выбранный период</div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TrafficChartCard;

