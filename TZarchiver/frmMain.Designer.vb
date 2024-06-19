<Global.Microsoft.VisualBasic.CompilerServices.DesignerGenerated()>
Partial Class frmMain
    Inherits System.Windows.Forms.Form

    'Form overrides dispose to clean up the component list.
    <System.Diagnostics.DebuggerNonUserCode()>
    Protected Overrides Sub Dispose(ByVal disposing As Boolean)
        Try
            If disposing AndAlso components IsNot Nothing Then
                components.Dispose()
            End If
        Finally
            MyBase.Dispose(disposing)
        End Try
    End Sub

    'Required by the Windows Form Designer
    Private components As System.ComponentModel.IContainer

    'NOTE: The following procedure is required by the Windows Form Designer
    'It can be modified using the Windows Form Designer.  
    'Do not modify it using the code editor.
    <System.Diagnostics.DebuggerStepThrough()>
    Private Sub InitializeComponent()
        Dim resources As System.ComponentModel.ComponentResourceManager = New System.ComponentModel.ComponentResourceManager(GetType(frmMain))
        Me.lstArchives = New System.Windows.Forms.ListBox()
        Me.btnExtract = New System.Windows.Forms.Button()
        Me.tvContents = New System.Windows.Forms.TreeView()
        Me.btnCreate = New System.Windows.Forms.Button()
        Me.btnRemove = New System.Windows.Forms.Button()
        Me.Label1 = New System.Windows.Forms.Label()
        Me.btnClear = New System.Windows.Forms.Button()
        Me.lnkGitHub = New System.Windows.Forms.LinkLabel()
        Me.Label2 = New System.Windows.Forms.Label()
        Me.Label3 = New System.Windows.Forms.Label()
        Me.Label4 = New System.Windows.Forms.Label()
        Me.SuspendLayout()
        '
        'lstArchives
        '
        Me.lstArchives.FormattingEnabled = True
        Me.lstArchives.ItemHeight = 15
        Me.lstArchives.Location = New System.Drawing.Point(10, 27)
        Me.lstArchives.Margin = New System.Windows.Forms.Padding(2, 2, 2, 2)
        Me.lstArchives.Name = "lstArchives"
        Me.lstArchives.Size = New System.Drawing.Size(214, 184)
        Me.lstArchives.TabIndex = 0
        '
        'btnExtract
        '
        Me.btnExtract.Location = New System.Drawing.Point(10, 216)
        Me.btnExtract.Margin = New System.Windows.Forms.Padding(2, 2, 2, 2)
        Me.btnExtract.Name = "btnExtract"
        Me.btnExtract.Size = New System.Drawing.Size(107, 46)
        Me.btnExtract.TabIndex = 2
        Me.btnExtract.Text = "Extract TZarc"
        Me.btnExtract.UseVisualStyleBackColor = True
        '
        'tvContents
        '
        Me.tvContents.Location = New System.Drawing.Point(308, 28)
        Me.tvContents.Margin = New System.Windows.Forms.Padding(2, 2, 2, 2)
        Me.tvContents.Name = "tvContents"
        Me.tvContents.Size = New System.Drawing.Size(249, 235)
        Me.tvContents.TabIndex = 4
        '
        'btnCreate
        '
        Me.btnCreate.Location = New System.Drawing.Point(122, 216)
        Me.btnCreate.Margin = New System.Windows.Forms.Padding(2, 2, 2, 2)
        Me.btnCreate.Name = "btnCreate"
        Me.btnCreate.Size = New System.Drawing.Size(102, 46)
        Me.btnCreate.TabIndex = 5
        Me.btnCreate.Text = "Create TZarc"
        Me.btnCreate.UseVisualStyleBackColor = True
        '
        'btnRemove
        '
        Me.btnRemove.Location = New System.Drawing.Point(230, 28)
        Me.btnRemove.Margin = New System.Windows.Forms.Padding(2, 2, 2, 2)
        Me.btnRemove.Name = "btnRemove"
        Me.btnRemove.Size = New System.Drawing.Size(72, 47)
        Me.btnRemove.TabIndex = 6
        Me.btnRemove.Text = "Remove item"
        Me.btnRemove.UseVisualStyleBackColor = True
        '
        'Label1
        '
        Me.Label1.Location = New System.Drawing.Point(230, 137)
        Me.Label1.Margin = New System.Windows.Forms.Padding(2, 0, 2, 0)
        Me.Label1.Name = "Label1"
        Me.Label1.Size = New System.Drawing.Size(72, 89)
        Me.Label1.TabIndex = 7
        Me.Label1.Text = "Drag && Drop files to extract and folders to create!"
        Me.Label1.TextAlign = System.Drawing.ContentAlignment.TopCenter
        '
        'btnClear
        '
        Me.btnClear.Location = New System.Drawing.Point(231, 80)
        Me.btnClear.Margin = New System.Windows.Forms.Padding(2, 2, 2, 2)
        Me.btnClear.Name = "btnClear"
        Me.btnClear.Size = New System.Drawing.Size(72, 47)
        Me.btnClear.TabIndex = 8
        Me.btnClear.Text = "Clear list"
        Me.btnClear.UseVisualStyleBackColor = True
        '
        'lnkGitHub
        '
        Me.lnkGitHub.AutoSize = True
        Me.lnkGitHub.Location = New System.Drawing.Point(164, 290)
        Me.lnkGitHub.Margin = New System.Windows.Forms.Padding(2, 0, 2, 0)
        Me.lnkGitHub.Name = "lnkGitHub"
        Me.lnkGitHub.Size = New System.Drawing.Size(244, 15)
        Me.lnkGitHub.TabIndex = 10
        Me.lnkGitHub.TabStop = True
        Me.lnkGitHub.Text = "https://github.com/SilverGreen93/TZarchiver"
        '
        'Label2
        '
        Me.Label2.AutoSize = True
        Me.Label2.Location = New System.Drawing.Point(212, 275)
        Me.Label2.Margin = New System.Windows.Forms.Padding(2, 0, 2, 0)
        Me.Label2.Name = "Label2"
        Me.Label2.Size = New System.Drawing.Size(148, 15)
        Me.Label2.TabIndex = 9
        Me.Label2.Text = "by SilverGreen93 (c) 2024"
        '
        'Label3
        '
        Me.Label3.AutoSize = True
        Me.Label3.Location = New System.Drawing.Point(10, 7)
        Me.Label3.Margin = New System.Windows.Forms.Padding(2, 0, 2, 0)
        Me.Label3.Name = "Label3"
        Me.Label3.Size = New System.Drawing.Size(109, 15)
        Me.Label3.TabIndex = 11
        Me.Label3.Text = "Processing queue:"
        '
        'Label4
        '
        Me.Label4.AutoSize = True
        Me.Label4.Location = New System.Drawing.Point(306, 7)
        Me.Label4.Margin = New System.Windows.Forms.Padding(2, 0, 2, 0)
        Me.Label4.Name = "Label4"
        Me.Label4.Size = New System.Drawing.Size(98, 15)
        Me.Label4.TabIndex = 12
        Me.Label4.Text = "Archive contents:"
        '
        'frmMain
        '
        Me.AllowDrop = True
        Me.AutoScaleDimensions = New System.Drawing.SizeF(7.0!, 15.0!)
        Me.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font
        Me.ClientSize = New System.Drawing.Size(567, 315)
        Me.Controls.Add(Me.Label4)
        Me.Controls.Add(Me.Label3)
        Me.Controls.Add(Me.lnkGitHub)
        Me.Controls.Add(Me.Label2)
        Me.Controls.Add(Me.btnClear)
        Me.Controls.Add(Me.Label1)
        Me.Controls.Add(Me.btnRemove)
        Me.Controls.Add(Me.btnCreate)
        Me.Controls.Add(Me.tvContents)
        Me.Controls.Add(Me.btnExtract)
        Me.Controls.Add(Me.lstArchives)
        Me.Font = New System.Drawing.Font("Microsoft Sans Serif", 9.0!, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, CType(204, Byte))
        Me.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedSingle
        Me.Icon = CType(resources.GetObject("$this.Icon"), System.Drawing.Icon)
        Me.Margin = New System.Windows.Forms.Padding(2, 2, 2, 2)
        Me.MaximizeBox = False
        Me.Name = "frmMain"
        Me.Text = "TZarchiver v1.3"
        Me.ResumeLayout(False)
        Me.PerformLayout()

    End Sub

    Friend WithEvents lstArchives As ListBox
    Friend WithEvents btnExtract As Button
    Friend WithEvents tvContents As TreeView
    Friend WithEvents btnCreate As Button
    Friend WithEvents btnRemove As Button
    Friend WithEvents Label1 As Label
    Friend WithEvents btnClear As Button
    Friend WithEvents lnkGitHub As LinkLabel
    Friend WithEvents Label2 As Label
    Friend WithEvents Label3 As Label
    Friend WithEvents Label4 As Label
End Class
