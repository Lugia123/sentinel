// Package blob — MinIO 对象存储:存/取大 HTML(AI 背调、财报解读)。
// 大 HTML 不入 PG,存本地 Docker MinIO。key 只在 server/.env。
package blob

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type Store struct {
	cli    *minio.Client
	bucket string
}

// New 连接 MinIO;若未配 endpoint 返回 nil(功能优雅降级)。
func New(endpoint, key, secret, bucket string) (*Store, error) {
	if endpoint == "" || key == "" {
		return nil, nil
	}
	cli, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(key, secret, ""),
		Secure: false,
	})
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ok, err := cli.BucketExists(ctx, bucket)
	if err != nil {
		return nil, fmt.Errorf("MinIO 连接失败: %w", err)
	}
	if !ok {
		if err := cli.MakeBucket(ctx, bucket, minio.MakeBucketOptions{}); err != nil {
			return nil, err
		}
	}
	return &Store{cli: cli, bucket: bucket}, nil
}

func (s *Store) Enabled() bool { return s != nil && s.cli != nil }

// PutHTML 存 HTML,返回 key。
func (s *Store) PutHTML(ctx context.Context, key, html string) error {
	r := bytes.NewReader([]byte(html))
	_, err := s.cli.PutObject(ctx, s.bucket, key, r, int64(len(html)),
		minio.PutObjectOptions{ContentType: "text/html; charset=utf-8"})
	return err
}

// GetHTML 取 HTML。
func (s *Store) GetHTML(ctx context.Context, key string) (string, error) {
	obj, err := s.cli.GetObject(ctx, s.bucket, key, minio.GetObjectOptions{})
	if err != nil {
		return "", err
	}
	defer obj.Close()
	b, err := io.ReadAll(obj)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

// Exists 判断 key 是否存在。
func (s *Store) Exists(ctx context.Context, key string) bool {
	_, err := s.cli.StatObject(ctx, s.bucket, key, minio.StatObjectOptions{})
	return err == nil
}
